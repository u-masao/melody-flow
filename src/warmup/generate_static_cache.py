import unsloth  # noqa: F401
import base64
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import sys

from bs4 import BeautifulSoup
from loguru import logger
import torch
from tqdm import tqdm
from transformers import LogitsProcessorList
import weave

from src.model.melody_processor import MelodyControlLogitsProcessor
from src.model.utils import load_model_and_tokenizer  # 共通関数をインポート

# デフォルトのハンドラを削除
logger.remove()
# 標準出力にINFOレベル以上を出力するハンドラを追加
logger.add(sys.stdout, level="INFO")


# --- パス設定 ---
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "dist"
APP_HTML_PATH = PROJECT_ROOT / "static" / "app.html"

# --- 設定項目 ---
MODEL_NAME = os.getenv("MODEL_NAME", None)

APP_ENV = os.getenv("APP_ENV", "development")
if APP_ENV == "production":
    VARIATIONS = range(1, 6)  # 本番は5個
    print(f"✅ Running in PRODUCTION mode: {len(VARIATIONS)} variations will be generated.")
else:
    VARIATIONS = range(1, 3)  # 開発中は2個
    print(f"🛠️ Running in DEVELOPMENT mode: {len(VARIATIONS)} variations will be generated.")

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


# --- 移調ロジック (変更なし) ---
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


# --- HTMLからコード進行リストを動的に取得 (変更なし) ---
def get_chord_progressions_from_html(file_path: Path) -> list[dict]:
    print(f"📄 Parsing chord progressions from: {file_path}")
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
        print(f"🎶 Found {len(progressions)} chord progressions.")
        return progressions
    except Exception as e:
        print(f"❌ Error parsing HTML: {e}")
        return []


# --- 生成ロジック (Weaveトレースを追加) ---
@weave.op()
def generate_midi_from_model(
    model, tokenizer, device, prompt: str, processor: MelodyControlLogitsProcessor, seed: int
) -> str:
    torch.manual_seed(seed)
    inputs = tokenizer(prompt, return_tensors="pt").to(device)
    logits_processors = LogitsProcessorList([processor])
    output = model.generate(
        **inputs,
        max_new_tokens=128,
        temperature=0.75,
        pad_token_id=tokenizer.eos_token_id,
        logits_processor=logits_processors,
    )
    # どの音を許可したかをWeaveのサマリーに記録
    weave.summary(
        {"allowed_notes": processor.note_tokenizer.ids_to_string(processor.allowed_token_ids)}
    )
    return tokenizer.decode(output[0])


def parse_and_encode_midi(decoded_text: str) -> str:
    match = re.search(r"pitch duration wait velocity instrument\s*\n(.*)", decoded_text, re.DOTALL)
    midi_note_data = match.group(1).strip() if match else decoded_text
    return base64.b64encode(midi_note_data.encode("utf-8")).decode("utf-8")


# --- メイン処理 ---
def main():
    # Weaveを初期化
    weave.init("melody-flow-cache-generator")

    # 共通関数でモデルを読み込む
    model, tokenizer, note_tokenizer_helper, device = load_model_and_tokenizer(MODEL_NAME)
    if not model:
        return

    chord_progressions = get_chord_progressions_from_html(APP_HTML_PATH)
    if not chord_progressions:
        print("Aborting: No chord progressions found.")
        return

    print("🚀 Starting static cache generation for all keys...")
    all_combinations = list(itertools.product(chord_progressions, ALL_KEYS, STYLES, VARIATIONS))

    for prog_info, target_key, style, var in tqdm(
        all_combinations, desc="Generating Cache", unit="file"
    ):
        original_prog = prog_info["progression"]
        original_key = prog_info["original_key"]

        transposed_prog = transpose_progression(original_prog, original_key, target_key)

        prog_hash = hashlib.md5(transposed_prog.encode()).hexdigest()
        output_path = OUTPUT_DIR / prog_hash / style
        os.makedirs(output_path, exist_ok=True)
        output_file = output_path / f"{var}.json"

        if os.path.exists(output_file):
            continue

        chords = [chord.strip() for chord in transposed_prog.split("-")]
        melodies = {}
        try:
            for chord in chords:
                processor = MelodyControlLogitsProcessor(chord, note_tokenizer_helper)
                prompt = (
                    f"style={style}, chord_progression={chord}\n"
                    "pitch duration wait velocity instrument\n"
                )
                raw_output = generate_midi_from_model(
                    model, tokenizer, device, prompt, processor, seed=var
                )
                encoded_midi = parse_and_encode_midi(raw_output)

                key = chord
                count = 2
                while key in melodies:
                    key = f"{chord}_{count}"
                    count += 1
                melodies[key] = encoded_midi

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump({"chord_melodies": melodies}, f)

        except Exception as e:
            tqdm.write(f"❌ FAILED to generate {output_file}: {e}")

    print("🎉 Static cache generation finished!")


if __name__ == "__main__":
    main()
