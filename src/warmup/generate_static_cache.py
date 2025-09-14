import unsloth  # noqa: F401
import base64
import hashlib
import itertools
import json
import os
from pathlib import Path
import re

from bs4 import BeautifulSoup
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, LogitsProcessorList
from unsloth import FastLanguageModel

from src.model.melody_processor import MelodyControlLogitsProcessor, NoteTokenizer

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


# --- HTMLからコード進行リストを動的に取得 ---
def get_chord_progressions_from_html(file_path: Path) -> list[str]:
    print(f"📄 Parsing chord progressions from: {file_path}")
    try:
        with open(file_path, encoding="utf-8") as f:
            soup = BeautifulSoup(f, "lxml")
        select_tag = soup.find("select", id="chord-progression")
        if not select_tag:
            raise ValueError("<select id='chord-progression'> not found.")
        options = select_tag.find_all("option")
        progressions = [opt["value"] for opt in options if "value" in opt.attrs]
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

    print("🚀 Starting static cache generation...")
    all_combinations = list(itertools.product(chord_progressions, STYLES, VARIATIONS))
    total = len(all_combinations)

    for i, (prog, style, var) in enumerate(all_combinations):
        prog_hash = hashlib.md5(prog.encode()).hexdigest()
        output_path = OUTPUT_DIR / prog_hash / style
        os.makedirs(output_path, exist_ok=True)
        output_file = output_path / f"{var}.json"

        if os.path.exists(output_file):
            print(f"[{i + 1}/{total}] ⏩ SKIPPED: {output_file} already exists.")
            continue

        print(f"[{i + 1}/{total}] 🎹 GENERATING: {output_file}...")
        chords = [chord.strip() for chord in prog.split("-")]
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

            with open(output_file, "w") as f:
                json.dump({"chord_melodies": melodies}, f)
            print(f"[{i + 1}/{total}] ✅ CREATED: {output_file}")
        except Exception as e:
            print(f"[{i + 1}/{total}] ❌ FAILED to generate {output_file}: {e}")

    print("🎉 Static cache generation finished!")


if __name__ == "__main__":
    main()
