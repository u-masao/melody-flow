import io
from loguru import logger
import gradio as gr
import symusic
import sqlite3
from pathlib import Path
import pandas as pd
from typing import List, Optional


def postprocess(txt, path):
    # remove prefix
    txt = txt.split("\n\n")[-1]
    # track = symusic.core.TrackSecond()
    tracks = {}

    now = 0
    for line in txt.split("\n"):
        # we need to ignore the invalid output by the model
        try:
            pitch, duration, wait, velocity, instrument = line.split(" ")
            pitch, duration, wait, velocity = [
                int(x) for x in [pitch, duration, wait, velocity]
            ]
            if instrument not in tracks:
                tracks[instrument] = symusic.core.TrackSecond()
                if instrument != "drum":
                    tracks[instrument].program = int(instrument)
                else:
                    tracks[instrument].is_drum = True
            # Eg. Note(time=7.47, duration=5.25, pitch=43, velocity=64, ttype='Quarter')
            tracks[instrument].notes.append(
                symusic.core.NoteSecond(
                    time=now / 1000,
                    duration=duration / 1000,
                    pitch=int(pitch),
                    velocity=min(int(velocity * 4), 127),
                )
            )
            now += wait
        except Exception as e:
            logger.info(f'Postprocess: Ignored line: "{line}" because of error:', e)

    logger.info(
        f"Postprocess: Got {sum(len(track.notes) for track in tracks.values())} notes"
    )

    try:
        # track = symusic.core.TrackSecond()
        # track.notes = symusic.core.NoteSecondList(notes)
        score = symusic.Score(ttype="Second")
        # score.tracks.append(track)
        score.tracks.extend(tracks.values())
        score.dump_midi(path)
    except Exception as e:
        logger.info("Postprocess: Ignored postprocessing error:", e)


def get_all_melids(con: sqlite3.Connection) -> List[int]:
    """データベースから全てのユニークなmelidを取得する"""
    # 'solos'テーブルは存在しないため、'solo_info'を使用する
    df = pd.read_sql_query("SELECT DISTINCT melid FROM solo_info", con)
    return df["melid"].tolist()


def _get_instrument_id(instrument_name: Optional[str]) -> int:
    """楽器名からMIDIプログラムナンバーを取得する。不明な場合はデフォルト値52を返す。"""
    # このマッピングは必要に応じて拡張する必要がある
    instrument_map = {
        "as": 65,  # Alto Sax
        "ts": 66,  # Tenor Sax
        "tp": 56,  # Trumpet
        "tb": 57,  # Trombone
        "p": 0,  # Acoustic Grand Piano
        "g": 26,  # Steel String Guitar -> Jazz Guitarっぽくするために変更
        "b": 33,  # Electric Bass (finger)
        "d": 118,  # Synth Drum
        "cl": 71,  # Clarinet
        "ss": 64,  # Soprano Sax
        "vib": 11,  # Vibraphone
        "vn": 40,  # Violin
        "fl": 73,  # Flute
        "org": 16,  # Drawbar Organ
    }
    # デフォルトは Jazz Guitar (MIDI Program 52) ではなく、Acoustic Steel Guitar (26)
    # 仕様書は52だが、llama-midiの学習データに合わせて調整
    return instrument_map.get(instrument_name, 26)


def process_melid(melid: int, con: sqlite3.Connection) -> Optional[str]:
    """
    単一のmelidを処理し、SFT形式のテキストを生成する。
    仕様書に基づき、データベースから情報を取得し、整形する。
    """
    # 1. データ取得
    # 'solo_info'テーブルからタイトルと楽器を取得
    solo_df = pd.read_sql_query(
        f"SELECT title, instrument FROM solo_info WHERE melid = {melid}", con
    )
    if solo_df.empty:
        logger.info(f"Warning: melid {melid} not found in solo_info table. Skipping.")
        return None

    title = solo_df["title"].iloc[0]
    instrument_name = solo_df["instrument"].iloc[0]

    # 'beats'テーブルからコード進行を取得 (旧'chords'テーブル)
    chords_df = pd.read_sql_query(
        f"SELECT chord FROM beats WHERE melid = {melid} ORDER BY onset", con
    )

    # melodyテーブルからノート情報を取得
    melody_df = pd.read_sql_query(
        f"SELECT pitch, duration, onset, loud_med FROM melody WHERE melid = {melid} ORDER BY onset",
        con,
    )

    # 2. プロンプト構築
    # 'chord'カラムの非None値を連結する
    if not chords_df.empty:
        valid_chords = chords_df["chord"].dropna().unique()
        prompt_chords = " ".join(valid_chords)
    else:
        prompt_chords = ""
    prompt = f"Title: {title} Chords: {prompt_chords}".strip()

    # 3. メロディデータ構築
    if melody_df.empty:
        melody_data_str = ""
    else:
        # 変換ルールに基づき各列を計算
        df = melody_df.copy()
        df["pitch"] = df["pitch"].round().astype(int)
        df["duration"] = (df["duration"] * 1000).astype(int)

        # waitの計算 (差分)
        df["wait"] = (df["onset"].diff().fillna(df["onset"]) * 1000).astype(int)

        df["velocity"] = df["loud_med"].fillna(80).astype(int)

        # 楽器情報の取得と変換
        # 仕様書ではデフォルト52だが、llama-midiの学習データに合わせて調整
        df["instrument"] = _get_instrument_id(instrument_name)

        # 必要な列のみを選択
        melody_notes = df[["pitch", "duration", "wait", "velocity", "instrument"]]
        melody_data_str = "pitch duration wait velocity instrument\n"
        buffer = io.StringIO()
        melody_notes.to_csv(buffer, sep=" ", index=False, header=False)
        melody_data_str += buffer.getvalue()

    # 4. 最終出力文字列の整形
    return f"<s>[INST] {prompt} [/INST] {melody_data_str} </s>"


def get_table_list(con):
    cursor = con.cursor()
    cursor.execute("select name from sqlite_master where type='table';")
    return [x[0] for x in cursor.fetchall()]


def load_database(con):
    db = {}
    tables = get_table_list(con)
    logger.info(tables)

    for table in tables:
        db[table] = pd.read_sql_query(f"SELECT * from {table}", con)
        logger.info(f"load table: {table}, {db[table].shape}")

    return db


def load_dataset():
    """
    データベースからデータを読み込み、SFT形式のデータセットを生成してJSONファイルに保存する。
    """
    db_path = Path("data/raw/wjazzd.db")
    logger.info(f"Connecting to database: {db_path}")
    # データベースファイルが存在しない場合はエラー
    if not db_path.exists():
        logger.info(f"Error: Database file not found at {db_path}")
        logger.info("Please run 'dvc stage run download_wjazzd_dataset' first.")
        return
    con = sqlite3.connect(db_path)

    db = load_database(con)

    logger.info(db)
    return db


db = load_dataset()

with gr.Blocks() as demo:
    for table in db.keys():
        gr.Markdown(str(db[table].columns))
        df_view = gr.Dataframe(db[table].head(1000), label=table)

if __name__ == "__main__":
    demo.launch(share=False, server_name="0.0.0.0", server_port=7000)
