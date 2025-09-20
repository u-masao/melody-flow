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
from transformers import AutoModelForCausalLM, AutoTokenizer, LogitsProcessorList
from unsloth import FastLanguageModel

from src.model.melody_processor import MelodyControlLogitsProcessor, NoteTokenizer

# デフォルトのハンドラを削除（INFOレベルでstderrに出力する設定）
logger.remove()

# 標準出力(stdout)にDEBUGレベル以上を出力するハンドラを追加
logger.add(sys.stdout, level="INFO")


# --- パス設定 (スクリプトの場所を基準にプロジェクトルートを決定) ---
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH_DEFAULT = PROJECT_ROOT / "models" / "llama-midi.pth/"
OUTPUT_DIR = PROJECT_ROOT / "dist"
APP_HTML_PATH = PROJECT_ROOT / "static" / "app.html"

# --- 設定項目 ---
MODEL_NAME = os.getenv("MODEL_NAME", str(MODEL_PATH_DEFAULT))

APP_ENV = os.getenv("APP_ENV", "development")
if APP_ENV == "production":
    VARIATIONS = range(1, 6)  # 本番は5個
    print(f"✅ Running in PRODUCTION mode: {len(VARIATIONS)} variations will be generated.")
else:
    VARIATIONS = range(1, 3)  # 開発中は2個
    print(f"🛠️ Running in DEVELOPMENT mode: {len(VARIATIONS)} variations will be generated.")

STYLES = ["JAZZ風", "POP風"]

# --- 移調ロジック用の定数 ---
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
    """コード名からルート音とクオリティを抽出する"""
    if not chord_name:
        return None, None
    match = re.match(r"([A-G][b#]?)", chord_name)
    if not match:
        return None, None
    root = match.group(1)
    quality = chord_name[len(root) :]
    return root, quality


def transpose_chord(chord_name: str, semitones: int, prefer_flats: bool = False) -> str:
    """単一のコードを移調する"""
    root, quality = parse_chord(chord_name)
    if root is None:
        return chord_name

    try:
        root_index = NOTES.index(root)
    except ValueError:
        try:
            root_index = NOTES_FLAT.index(root)
        except ValueError:
            return chord_name  # 知らないルート音

    new_root_index = (root_index + semitones + 12) % 12

    sharp_note = NOTES[new_root_index]
    flat_note = NOTES_FLAT[new_root_index]

    new_root = flat_note if prefer_flats and sharp_note != flat_note else sharp_note

    return new_root + quality


def transpose_progression(prog_string: str, original_key: str, target_key: str) -> str:
    """コード進行全体を指定されたキーに移調する"""
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
    """HTMLからプリセットのコード進行と元のキーをパースする"""
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
                    key = parts[0].strip()
                    prog = parts[1].strip()
                    progressions.append({"original_key": key, "progression": prog})
        print(f"🎶 Found {len(progressions)} chord progressions.")
        return progressions
    except Exception as e:
        print(f"❌ Error parsing HTML: {e}")
        return []


# --- モデル読み込み ---
def load_model():
    print(f"🧠 Loading model: {MODEL_NAME}...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"🔥 Using device: {device}")

    try:
        model, tokenizer = None, None
        if os.path.isdir(MODEL_NAME):
            print("-> Loading as local Unsloth model (4-bit)...")
            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name=MODEL_NAME, max_seq_length=4096, dtype=None, load_in_4bit=True
            )
        else:
            print(f"-> Loading as Hugging Face Hub model ({MODEL_NAME})...")
            model = AutoModelForCausalLM.from_pretrained(
                MODEL_NAME, torch_dtype=torch.bfloat16
            ).to(device)
            tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

        note_tokenizer_helper = NoteTokenizer(tokenizer)
        print("✅ Model loaded successfully.")
        return model, tokenizer, note_tokenizer_helper, device
    except Exception as e:
        print(f"❌ Fatal: Error loading model: {e}")
        return None, None, None, None


# --- 生成ロジック ---
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
    return tokenizer.decode(output[0])


def parse_and_encode_midi(decoded_text: str) -> str:
    match = re.search(r"pitch duration wait velocity instrument\s*\n(.*)", decoded_text, re.DOTALL)
    midi_note_data = match.group(1).strip() if match else decoded_text
    return base64.b64encode(midi_note_data.encode("utf-8")).decode("utf-8")


# --- メイン処理 ---
def main():
    model, tokenizer, note_tokenizer_helper, device = load_model()
    if not model:
        return

    chord_progressions = get_chord_progressions_from_html(APP_HTML_PATH)
    if not chord_progressions:
        print("Aborting: No chord progressions found.")
        return

    print("🚀 Starting static cache generation for all keys...")
    all_combinations = list(itertools.product(chord_progressions, ALL_KEYS, STYLES, VARIATIONS))

    # tqdmでループをラップしてプログレスバーを表示
    for prog_info, target_key, style, var in tqdm(
        all_combinations, desc="Generating Cache", unit="file"
    ):
        original_prog = prog_info["progression"]
        original_key = prog_info["original_key"]

        # コード進行をターゲットのキーに移調
        transposed_prog = transpose_progression(original_prog, original_key, target_key)

        # 移調後のコード進行でハッシュを生成
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
            # エラーが発生した場合はプログレスバーを壊さずに出力
            tqdm.write(f"❌ FAILED to generate {output_file}: {e}")

    print("🎉 Static cache generation finished!")


if __name__ == "__main__":
    main()
