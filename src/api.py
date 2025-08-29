# src/api.py
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict
import uvicorn
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, LogitsProcessorList
import base64
import re
import os
import time
# --- 【変更】NoteTokenizerもインポート ---
from .melody_processor import MelodyControlLogitsProcessor, NoteTokenizer

# --- AIモデルのセットアップ ---
MODEL_NAME = "dx2102/llama-midi"
print(f"Loading model: {MODEL_NAME}...")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {DEVICE}")
try:
    TOKENIZER = AutoTokenizer.from_pretrained(MODEL_NAME)
    MODEL = AutoModelForCausalLM.from_pretrained(MODEL_NAME).to(DEVICE)
    # --- 【追加】NoteTokenizerのインスタンスを作成 ---
    NOTE_TOKENIZER_HELPER = NoteTokenizer(TOKENIZER)
    print("Model loaded successfully.")
except Exception as e:
    print(f"Error loading model: {e}")
    TOKENIZER, MODEL, NOTE_TOKENIZER_HELPER = None, None, None

# --- FastAPIアプリケーション (変更なし) ---
app = FastAPI(title="Melody Flow API")

# --- 静的ファイル配信 (変更なし) ---
current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, '..', 'static')
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# --- APIデータモデル (変更なし) ---
class MelodyGenerationRequest(BaseModel):
    chord_progression: str
    style: str

class MelodyGenerationResponse(BaseModel):
    chord_melodies: Dict[str, str]
    raw_outputs: Dict[str, str]

# --- ヘルパー関数 (変更なし) ---
def generate_midi_from_model(prompt: str, processor: MelodyControlLogitsProcessor) -> str:
    if not MODEL or not TOKENIZER:
        raise RuntimeError("Model is not loaded.")
    inputs = TOKENIZER(prompt, return_tensors="pt").to(DEVICE)
    logits_processors = LogitsProcessorList([processor])
    output = MODEL.generate(
        **inputs,
        max_new_tokens=128,
        temperature=0.75,
        pad_token_id=TOKENIZER.eos_token_id,
        logits_processor=logits_processors
    )
    return TOKENIZER.decode(output[0])

def parse_and_encode_midi(decoded_text: str) -> str:
    match = re.search(r'pitch duration wait velocity instrument\s*\n(.*)', decoded_text, re.DOTALL)
    midi_note_data = match.group(1).strip() if match else decoded_text
    return base64.b64encode(midi_note_data.encode('utf-8')).decode('utf-8')

# --- APIエンドポイント ---
@app.get("/", response_class=FileResponse)
async def read_index():
    return FileResponse(os.path.join(static_dir, 'index.html'))

@app.post("/generate", response_model=MelodyGenerationResponse)
def generate_melody(request: MelodyGenerationRequest):
    total_start_time = time.time()
    chords = [chord.strip() for chord in request.chord_progression.split('-')]
    melodies = {}
    raw_outputs = {}
    print(f"Generating melodies for chords: {chords}")

    for chord in chords:
        chord_start_time = time.time()

        # --- 【変更】NOTE_TOKENIZER_HELPER を使用 ---
        processor = MelodyControlLogitsProcessor(chord, NOTE_TOKENIZER_HELPER)
        
        prompt = f"style={request.style}, chord_progression={chord}\npitch duration wait velocity instrument\n"
        raw_output = generate_midi_from_model(prompt, processor)
        encoded_midi = parse_and_encode_midi(raw_output)

        key = chord
        count = 2
        while key in melodies:
            key = f"{chord}_{count}"
            count += 1
        melodies[key] = encoded_midi
        raw_outputs[key] = raw_output
        
        chord_end_time = time.time()
        print(f"  - Generated for {key} in {chord_end_time - chord_start_time:.2f} seconds")

    total_end_time = time.time()
    print(f"Total generation time: {total_end_time - total_start_time:.2f} seconds")

    return MelodyGenerationResponse(chord_melodies=melodies, raw_outputs=raw_outputs)

# --- サーバー起動 (変更なし) ---
if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)

