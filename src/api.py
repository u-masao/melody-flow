# src/api.py
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict # Dictをインポート
import uvicorn
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import base64
import re
import os

# --- AIモデルのセットアップ (変更なし) ---
MODEL_NAME = "dx2102/llama-midi"
print(f"Loading model: {MODEL_NAME}...")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {DEVICE}")
try:
    TOKENIZER = AutoTokenizer.from_pretrained(MODEL_NAME)
    MODEL = AutoModelForCausalLM.from_pretrained(MODEL_NAME).to(DEVICE)
    print("Model loaded successfully.")
except Exception as e:
    print(f"Error loading model: {e}")
    TOKENIZER, MODEL = None, None

# --- FastAPIアプリケーション ---
app = FastAPI(title="Melody Flow API")

# --- 静的ファイル配信 (変更なし) ---
current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, '..', 'static')
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# --- APIデータモデル ---
class MelodyGenerationRequest(BaseModel):
    chord_progression: str
    style: str

# 【変更】レスポンスの型を、コード名をキーとする辞書に変更
class MelodyGenerationResponse(BaseModel):
    chord_melodies: Dict[str, str] # 例: {"C": "base64_data", "G": "base64_data"}
    raw_outputs: Dict[str, str]

# --- ヘルパー関数 (変更なし) ---
def generate_midi_from_model(prompt: str) -> str:
    if not MODEL or not TOKENIZER:
        raise RuntimeError("Model is not loaded.")
    inputs = TOKENIZER(prompt, return_tensors="pt").to(DEVICE)
    output = MODEL.generate(
        **inputs, max_new_tokens=128, temperature=0.75, pad_token_id=TOKENIZER.eos_token_id
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
    """
    【変更】コード進行をパースし、コードごとにメロディを生成する
    """
    # "C - G - Am - F" のような文字列を ["C", "G", "Am", "F"] のリストに変換
    chords = [chord.strip() for chord in request.chord_progression.split('-')]
    
    melodies = {}
    raw_outputs = {}

    print(f"Generating melodies for chords: {chords}")

    for chord in chords:
        # コードごとにプロンプトを作成
        prompt = f"style={request.style}, chord_progression={chord}\npitch duration wait velocity instrument\n"
        
        # モデルを呼び出し
        raw_output = generate_midi_from_model(prompt)
        encoded_midi = parse_and_encode_midi(raw_output)
        
        # 結果を保存
        # 同じコードが複数回出てくる場合を考慮し、ユニークなキーにする (例: "Am_2")
        key = chord
        count = 2
        while key in melodies:
            key = f"{chord}_{count}"
            count += 1
        
        melodies[key] = encoded_midi
        raw_outputs[key] = raw_output
        print(f"  - Generated for {key}")

    return MelodyGenerationResponse(chord_melodies=melodies, raw_outputs=raw_outputs)

# --- サーバー起動 ---
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

