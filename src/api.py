# src/api.py
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse # FileResponseを追加
from fastapi.staticfiles import StaticFiles # StaticFilesを追加
from pydantic import BaseModel
import uvicorn
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import base64
import re
import os # osモジュールを追加

# --- AIモデルのセットアップ ---
# (ここは変更ありません)
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
    TOKENIZER = None
    MODEL = None

# --- FastAPIアプリケーションのインスタンス化 ---
app = FastAPI(
    title="Melody Flow API",
    description="リズム入力からメロディを生成するAIのAPIです。",
    version="0.1.0",
)

# --- 静的ファイルの配信設定 ---
# 【追加】'static'という名前のディレクトリを静的ファイル置き場としてマウントします
# このコードがある場所からの相対パスで'static'ディレクトリを指定します
# 実行場所によってパスが変わるのを防ぐため、このファイルのディレクトリを基準にします
current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, '..', 'static') # srcディレクトリの一つ上の階層のstatic
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# --- APIリクエスト/レスポンスのデータモデル ---
# (ここは変更ありません)
class MelodyGenerationRequest(BaseModel):
    chord_progression: str
    style: str

class MelodyGenerationResponse(BaseModel):
    midi_data: str
    raw_output: str

# --- ヘルパー関数 ---
# (ここは変更ありません)
def generate_midi_from_model(prompt: str) -> str:
    if not MODEL or not TOKENIZER:
        raise RuntimeError("Model is not loaded. Cannot generate MIDI.")
    print("Generating MIDI data...")
    inputs = TOKENIZER(prompt, return_tensors="pt").to(DEVICE)
    output = MODEL.generate(
        **inputs, max_new_tokens=256, temperature=0.75, pad_token_id=TOKENIZER.eos_token_id
    )
    decoded_output = TOKENIZER.decode(output[0])
    print("Generation complete.")
    return decoded_output

def parse_and_encode_midi(decoded_text: str) -> str:
    match = re.search(r'pitch duration wait velocity instrument\s*\n(.*)', decoded_text, re.DOTALL)
    if match:
        midi_note_data = match.group(1).strip()
    else:
        print("Warning: Could not find MIDI header.")
        midi_note_data = decoded_text
    midi_binary = midi_note_data.encode('utf-8')
    midi_base64 = base64.b64encode(midi_binary).decode('utf-8')
    return midi_base64

# --- APIエンドポイント ---
# 【変更】ルートパス('/')にアクセスされたら、index.htmlを返すようにします
@app.get("/", response_class=FileResponse)
async def read_index():
    return FileResponse(os.path.join(static_dir, 'index.html'))

@app.post("/generate", response_model=MelodyGenerationResponse)
def generate_melody(request: MelodyGenerationRequest):
    prompt = f"style={request.style}, chord_progression={request.chord_progression}\npitch duration wait velocity instrument\n"
    print(f"Received request with prompt: {prompt}")
    raw_model_output = generate_midi_from_model(prompt)
    midi_base64_data = parse_and_encode_midi(raw_model_output)
    return MelodyGenerationResponse(
        midi_data=midi_base64_data,
        raw_output=raw_model_output
    )

# --- サーバーの起動 ---
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)


