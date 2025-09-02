import argparse
import json
import io
import sqlite3
from pathlib import Path
import pandas as pd
from typing import List, Optional


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
        print(f"Warning: melid {melid} not found in solo_info table. Skipping.")
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

        # waitの計算 (次の音の開始時刻との差分)
        # onsetは秒単位なので、waitも秒単位で計算してからミリ秒に変換する
        wait_in_seconds = df["onset"].shift(-1) - df["onset"]
        # 最後の音のwaitは、その音のduration(秒)とする
        # df['duration']はこの時点では秒単位
        wait_in_seconds.fillna(df["duration"], inplace=True)
        df["wait"] = (wait_in_seconds * 1000).astype(int)

        # durationをミリ秒に変換
        df["duration"] = (df["duration"] * 1000).astype(int)

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


def main(db_path: Path, output_path: Path):
    """
    データベースからデータを読み込み、SFT形式のデータセットを生成してJSONファイルに保存する。
    """
    print(f"Connecting to database: {db_path}")
    # データベースファイルが存在しない場合はエラー
    if not db_path.exists():
        print(f"Error: Database file not found at {db_path}")
        print("Please run 'dvc stage run download_wjazzd_dataset' first.")
        return
    con = sqlite3.connect(db_path)

    print("Fetching all melids...")
    melids = get_all_melids(con)

    # For development, let's process only a small subset
    # melids = melids[:10]

    results = []
    print(f"Processing {len(melids)} melids...")
    for melid in melids:
        sft_text = process_melid(melid, con)
        if sft_text:
            results.append({"text": sft_text})

    con.close()

    print(f"Saving dataset to {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("Dataset creation complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="WJazzDデータセットからSFT用テキストを生成するスクリプト"
    )
    parser.add_argument(
        "db_path", type=str, help="入力SQLiteデータベースファイルのパス"
    )
    parser.add_argument("output_path", type=str, help="出力JSONファイルのパス")
    args = parser.parse_args()

    main(Path(args.db_path), Path(args.output_path))
