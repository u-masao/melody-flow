import unsloth  # noqa: F401
import io
import matplotlib.pyplot as plt
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import sys

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from loguru import logger
from src.model.utils import load_model_and_tokenizer  # 共通関数をインポート
from src.api.main import generate_melody
from fastapi import Response
from tqdm import tqdm
import wandb
import weave
from src.model.visualize import plot_melodies

load_dotenv()

# デフォルトのハンドラを削除
logger.remove()
# 標準出力にINFOレベル以上を出力するハンドラを追加
logger.add(sys.stdout, level="INFO")

run = wandb.init(entity=os.environ["WANDB_ENTITY"], project=os.environ["WANDB_PROJECT"])


# --- パス設定 ---
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "dist"
APP_HTML_PATH = PROJECT_ROOT / "static" / "app.html"

# --- 設定項目 ---
MODEL_NAME = os.getenv("MODEL_NAME", None)

APP_ENV = os.getenv("APP_ENV", "development")
if APP_ENV == "production":
    VARIATIONS = range(1, 6)  # 本番は5個
    logger.info(f"✅ Running in PRODUCTION mode: {len(VARIATIONS)} variations will be generated.")
else:
    VARIATIONS = range(1, 3)  # 開発中は2個
    logger.info(f"🛠️ Running in DEVELOPMENT mode: {len(VARIATIONS)} variations will be generated.")

STYLES = ["JAZZ風", "POP風"]

# --- 移調ロジック用の定数 (変更なし) ---
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
ALL_KEYS = [
    "C",
    "C#",
    "Db",
    "D",
    "D#",
    "Eb",
    "E",
    "F",
    "F#",
    "Gb",
    "G",
    "G#",
    "Ab",
    "A",
    "A#",
    "Bb",
    "B",
]


# --- 移調ロジック ---
def parse_chord(chord_name: str) -> tuple[str | None, str | None]:
    if not chord_name:
        return None, None
    match = re.match(r"([A-G][b#]?)", chord_name)
    if not match:
        return None, None
    root = match.group(1)
    quality = chord_name[len(root) :]
    return root, quality


def transpose_chord(chord_name: str, semitones: int, prefer_flats: bool = False) -> str:
    root, quality = parse_chord(chord_name)
    if root is None:
        return chord_name
    try:
        root_index = NOTES.index(root)
    except ValueError:
        try:
            root_index = NOTES_FLAT.index(root)
        except ValueError:
            return chord_name
    new_root_index = (root_index + semitones + 12) % 12
    sharp_note = NOTES[new_root_index]
    flat_note = NOTES_FLAT[new_root_index]
    new_root = flat_note if prefer_flats and sharp_note != flat_note else sharp_note
    return new_root + quality


def transpose_progression(prog_string: str, original_key: str, target_key: str) -> str:
    try:
        original_key_index = NOTES.index(original_key)
    except ValueError:
        original_key_index = NOTES_FLAT.index(original_key)
    try:
        target_key_index = NOTES.index(target_key)
    except ValueError:
        target_key_index = NOTES_FLAT.index(target_key)
    semitones = target_key_index - original_key_index
    if semitones == 0:
        return prog_string
    flat_keys = ["F", "Bb", "Eb", "Ab", "Db", "Gb"]
    prefer_flats = target_key in flat_keys or "b" in target_key
    original_chords = [c.strip() for c in prog_string.split("-")]
    transposed_chords = [transpose_chord(c, semitones, prefer_flats) for c in original_chords]
    return " - ".join(transposed_chords)


# --- HTMLからコード進行リストを動的に取得 ---
def get_chord_progressions_from_html(file_path: Path) -> list[dict]:
    logger.info(f"📄 Parsing chord progressions from: {file_path}")
    try:
        with open(file_path, encoding="utf-8") as f:
            soup = BeautifulSoup(f, "lxml")
        select_tag = soup.find("select", id="chord-progression")
        if not select_tag:
            raise ValueError("<select id='chord-progression'> not found.")
        options = select_tag.find_all("option")
        progressions = []
        for opt in options:
            if "value" in opt.attrs and ":" in opt["value"]:
                parts = opt["value"].split(":", 1)
                if len(parts) == 2:
                    key, prog = parts[0].strip(), parts[1].strip()
                    progressions.append({"original_key": key, "progression": prog})
        logger.info(f"🎶 Found {len(progressions)} chord progressions.")
        return progressions
    except Exception as e:
        logger.error(f"❌ Error parsing HTML: {e}")
        return []


@weave.op()
def plot_melodies_weave(response):
    fig = plot_melodies(response)
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


# --- メイン処理 ---
def main(
    supress_token_prob_ratio: float = 0.3,
    instrument: str = "Alto Saxophone",
):
    # Weaveを初期化
    weave.init(os.environ["WANDB_PROJECT"])

    # 共通関数でモデルを読み込む
    model, tokenizer, note_tokenizer_helper, device = load_model_and_tokenizer(MODEL_NAME)
    if not model:
        return

    # APP HTML からコード進行を読み込む
    chord_progressions = get_chord_progressions_from_html(APP_HTML_PATH)
    if not chord_progressions:
        logger.info("Aborting: No chord progressions found.")
        return

    # 全ての組み合わせを作成
    logger.info("🚀 Starting static cache generation for all keys...")
    all_combinations = list(itertools.product(chord_progressions, ALL_KEYS, STYLES, VARIATIONS))

    with tqdm(all_combinations, desc="Generating Cache", unit="file") as pbar:
        for prog_info, target_key, style, var in pbar:
            # 変数を作成
            original_prog = prog_info["progression"]
            original_key = prog_info["original_key"]
            transposed_prog = transpose_progression(original_prog, original_key, target_key)
            prog_hash = hashlib.md5(transposed_prog.encode()).hexdigest()

            # プログレスバーを更新
            pbar.set_description(f"Hash: {prog_hash}, Style: {style}, Variation: {var}")

            # ファイル名を作成
            output_path = OUTPUT_DIR / prog_hash / style
            os.makedirs(output_path, exist_ok=True)
            output_file = output_path / f"{var}.json"
            png_file = output_path / f"{var}.png"

            # ファイル存在チェック
            if os.path.exists(output_file):
                continue

            # メロディを生成(API 呼び出し)
            response = generate_melody(
                Response,
                chord_progression=transposed_prog,
                style=style,
                variation=var,
                supress_token_prob_ratio=supress_token_prob_ratio,
                instrument=instrument,
            )

            # ファイルに保存
            try:
                with open(output_file, "w", encoding="utf-8") as fo:
                    json.dump(response, fo)
                buf = plot_melodies_weave(response)
                with open(png_file, "wb") as fo:
                    fo.write(buf)

            except Exception as e:
                tqdm.write(f"❌ FAILED to generate {output_file}: {e}")

    logger.info("🎉 Static cache generation finished!")


if __name__ == "__main__":
    main()
