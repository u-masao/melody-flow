import sqlite3
from pathlib import Path
import pandas as pd
import pytest
from unittest.mock import patch, mock_open, MagicMock

from src.model.make_dataset import (
    _get_instrument_id,
    get_all_melids,
    process_melid,
    main,
)


@pytest.fixture
def memory_db():
    """
    メモリ上に一時的なSQLiteデータベースを作成し、
    必要なテーブルをセットアップするpytestフィクスチャ。
    """
    con = sqlite3.connect(":memory:")
    cur = con.cursor()

    # テーブル作成
    cur.execute(
        """
        CREATE TABLE solo_info (
            melid INTEGER PRIMARY KEY,
            title TEXT,
            instrument TEXT
        )
    """
    )
    cur.execute(
        """
        CREATE TABLE beats (
            melid INTEGER,
            onset REAL,
            chord TEXT
        )
    """
    )
    cur.execute(
        """
        CREATE TABLE melody (
            melid INTEGER,
            pitch REAL,
            duration REAL,
            onset REAL,
            loud_med REAL
        )
    """
    )

    con.commit()
    yield con
    con.close()


def test_get_instrument_id():
    """_get_instrument_idが楽器名を正しくMIDIプログラムナンバーに変換するかテスト"""
    assert _get_instrument_id("as") == 65
    assert _get_instrument_id("p") == 0
    # 未知の楽器はデフォルト値26を返す
    assert _get_instrument_id("unknown_instrument") == 26
    # Noneが渡された場合もデフォルト値
    assert _get_instrument_id(None) == 26


def test_get_all_melids(memory_db):
    """get_all_melidsがデータベースから全てのユニークなmelidを取得するかテスト"""
    # テストデータ準備
    test_data = [(1, "title1", "as"), (2, "title2", "ts"), (3, "title3", "p")]
    memory_db.executemany("INSERT INTO solo_info VALUES (?, ?, ?)", test_data)
    memory_db.commit()

    # 実行と検証
    melids = get_all_melids(memory_db)
    assert sorted(melids) == [1, 2, 3]


def test_process_melid_happy_path(memory_db):
    """process_melidが正常系のデータを正しく処理できるかテスト"""
    # テストデータ準備
    memory_db.execute("INSERT INTO solo_info VALUES (1, 'Test Title', 'as')")
    memory_db.execute("INSERT INTO beats VALUES (1, 0.0, 'Cmaj7'), (1, 2.0, 'Fmaj7')")
    memory_db.execute(
        "INSERT INTO melody VALUES (1, 72.1, 0.5, 0.0, 90), (1, 74.0, 0.4, 0.5, 85)"
    )
    memory_db.commit()

    # 実行
    result = process_melid(1, memory_db)

    # 検証
    assert result is not None
    assert result.startswith("<s>[INST] Title: Test Title Chords: Cmaj7 Fmaj7 [/INST]")
    assert result.endswith("</s>")
    # メロディ部分の検証
    melody_part = result.split("[/INST]")[1].strip()
    expected_melody = (
        "pitch duration wait velocity instrument\n"
        "72 500 500 90 65\n"
        "74 400 400 85 65\n"
    )
    assert melody_part.startswith(expected_melody)


def test_process_melid_no_melody(memory_db):
    """メロディデータが存在しない場合に正しく処理されるかテスト"""
    memory_db.execute("INSERT INTO solo_info VALUES (2, 'No Melody Title', 'p')")
    memory_db.execute("INSERT INTO beats VALUES (2, 0.0, 'Am7')")
    memory_db.commit()

    result = process_melid(2, memory_db)
    assert result == "<s>[INST] Title: No Melody Title Chords: Am7 [/INST]  </s>"


def test_process_melid_no_chords(memory_db):
    """コードデータが存在しない場合に正しく処理されるかテスト"""
    memory_db.execute("INSERT INTO solo_info VALUES (3, 'No Chord Title', 'g')")
    memory_db.execute("INSERT INTO melody VALUES (3, 60, 1.0, 0.0, 80)")
    memory_db.commit()

    result = process_melid(3, memory_db)
    assert result.startswith("<s>[INST] Title: No Chord Title [/INST]")


def test_process_melid_not_found(memory_db):
    """指定したmelidが存在しない場合にNoneを返すかテスト"""
    result = process_melid(999, memory_db)
    assert result is None


def test_process_melid_single_note_wait_calculation(memory_db):
    """単一ノートのwait時間が正しくdurationから計算されるかテスト"""
    memory_db.execute("INSERT INTO solo_info VALUES (4, 'Single Note', 'ts')")
    memory_db.execute("INSERT INTO melody VALUES (4, 70, 0.8, 0.0, 88)")
    memory_db.commit()

    result = process_melid(4, memory_db)
    melody_part = result.split("instrument\n")[1]
    # wait(800)がduration(800)と同じ値になるはず
    assert melody_part.strip().startswith("70 800 800 88 66")


@patch("src.model.make_dataset.get_all_melids")
@patch("src.model.make_dataset.process_melid")
@patch("src.model.make_dataset.sqlite3")
def test_main_flow(mock_sqlite3, mock_process_melid, mock_get_all_melids):
    """main関数が全体の流れを正しく制御するかテスト"""
    # モックの設定
    mock_con = MagicMock()
    mock_sqlite3.connect.return_value = mock_con

    # Pathオブジェクトのモック
    mock_db_path = MagicMock(spec=Path)
    mock_db_path.exists.return_value = True
    mock_output_path = MagicMock(spec=Path)

    mock_get_all_melids.return_value = [1, 2]
    # 2番目のmelidは処理に失敗するケースを模倣
    mock_process_melid.side_effect = ["processed_data_1", None]

    # openをモック化して書き込み内容をキャプチャ
    m = mock_open()
    with patch("builtins.open", m):
        main(mock_db_path, mock_output_path)

    # 検証
    mock_db_path.exists.assert_called_once()
    mock_sqlite3.connect.assert_called_once_with(mock_db_path)
    mock_get_all_melids.assert_called_once_with(mock_con)
    assert mock_process_melid.call_count == 2
    mock_con.close.assert_called_once()

    # JSON出力の検証
    mock_output_path.parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)
    m.assert_called_once_with(mock_output_path, "w", encoding="utf-8")

    # 書き込まれた内容を確認
    handle = m()
    written_data = "".join(call.args[0] for call in handle.write.call_args_list)
    import json
    loaded_data = json.loads(written_data)

    # 処理に成功した "processed_data_1" のみ含まれる
    assert loaded_data == [{"text": "processed_data_1"}]


@patch("src.model.make_dataset.print")
def test_main_db_not_found(mock_print):
    """main関数がDBファイル不在時にエラーメッセージを表示して終了するかテスト"""
    mock_db_path = MagicMock(spec=Path)
    mock_db_path.exists.return_value = False
    mock_output_path = MagicMock(spec=Path)

    main(mock_db_path, mock_output_path)

    mock_print.assert_any_call(f"Error: Database file not found at {mock_db_path}")
