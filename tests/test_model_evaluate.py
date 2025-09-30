import os
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
from src.model.evaluate import MelodyGenerator


@pytest.fixture
def mock_dependencies():
    """MelodyGeneratorの初期化に必要な依存関係をモック化するフィクスチャ"""
    return {
        "model": MagicMock(),
        "tokenizer": MagicMock(),
        "note_tokenizer_helper": MagicMock(),
        "device": "cpu",
        "soundfont_path": "dummy/path/to/soundfont.sf2",
    }


@pytest.fixture
def melody_generator(mock_dependencies):
    """テスト用のMelodyGeneratorインスタンスを生成するフィクスチャ"""
    # AudioUtilityのインスタンス化をモック
    with patch("src.model.evaluate.AudioUtility"):
        gen = MelodyGenerator(**mock_dependencies)
        # 内部で作成されるaudio_utilインスタンスも差し替える
        gen.audio_util = MagicMock()
        return gen


@pytest.fixture
def sample_parsed_notes():
    """テスト用のサンプルノートデータを提供するフィクスチャ"""
    return [
        {"pitch": 60, "duration": 480, "wait": 0, "velocity": 100, "instrument": 0},
        {"pitch": 62, "duration": 480, "wait": 500, "velocity": 100, "instrument": 0},
    ]


@patch("src.model.evaluate.os")
@patch("src.model.evaluate.tempfile")
@patch("builtins.open", new_callable=mock_open, read_data=b"fake_wav_data")
def test_create_wav_from_notes_success(
    mock_open_builtin,
    mock_tempfile,
    mock_os,
    melody_generator,
    sample_parsed_notes,
):
    """
    正常系テスト: _create_wav_from_notesが有効なノートリストからWAVデータを返すことを確認
    """
    fake_temp_dir = "/tmp/fake_dir"
    mock_tempfile.mkdtemp.return_value = fake_temp_dir
    mock_os.listdir.return_value = ["temp.mid", "temp.wav"]  # これらはクリーンアップされる
    mock_os.path.join.side_effect = os.path.join  # os.path.joinを本物の動作に戻す

    result_data = melody_generator._create_wav_from_notes(sample_parsed_notes)

    # 戻り値がbytesデータであることを確認
    assert result_data == b"fake_wav_data"

    melody_generator.audio_util.create_midi_file.assert_called_once()
    melody_generator.audio_util.midi_to_wav.assert_called_once()
    # open()がPathオブジェクトを引数にして呼ばれることを確認
    mock_open_builtin.assert_any_call(Path(fake_temp_dir) / "temp.wav", "rb")
    mock_os.listdir.assert_called_once_with(fake_temp_dir)
    assert mock_os.remove.call_count == 2  # midとwavの2つを削除
    mock_os.rmdir.assert_called_once_with(fake_temp_dir)


def test_create_wav_from_notes_empty_input(melody_generator):
    """
    境界系テスト: 空のノートリストが与えられた場合にNoneを返すことを確認
    """
    assert melody_generator._create_wav_from_notes([]) is None


@patch("src.model.evaluate.os")
@patch("src.model.evaluate.tempfile")
def test_create_wav_from_notes_audio_util_error(
    mock_tempfile,
    mock_os,
    melody_generator,
    sample_parsed_notes,
):
    """
    異常系テスト: AudioUtilityで例外が発生した場合にNoneを返し、
    ファイルをクリーンアップすることを確認
    """
    mock_tempfile.mkdtemp.return_value = "/tmp/fake_dir"
    # エラー時でもクリーンアップ処理が走るので、リストは空ではない可能性もあるが、
    # いずれにせよrmdirが呼ばれることを確認するのが目的
    mock_os.listdir.return_value = ["some_file.mid"]
    mock_os.path.join.side_effect = os.path.join
    melody_generator.audio_util.create_midi_file.side_effect = Exception("MIDI creation failed")

    result = melody_generator._create_wav_from_notes(sample_parsed_notes)

    assert result is None
    mock_os.listdir.assert_called_once_with("/tmp/fake_dir")
    mock_os.remove.assert_called_once_with("/tmp/fake_dir/some_file.mid")
    mock_os.rmdir.assert_called_once_with("/tmp/fake_dir")
