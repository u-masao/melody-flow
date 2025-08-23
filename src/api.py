# src/api.py
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import base64
import re

# --- AIモデルのセットアップ ---
# サーバー起動時に一度だけモデルを読み込みます。
# これにより、APIリクエストごとの読み込みコストをなくします。
# ------------------------------------
MODEL_NAME = "dx2102/llama-midi"
print(f"Loading model: {MODEL_NAME}...")

# GPUが利用可能かチェック
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {DEVICE}")

# モデルとトークナイザーをグローバル変数としてロード
try:
    TOKENIZER = AutoTokenizer.from_pretrained(MODEL_NAME)
    MODEL = AutoModelForCausalLM.from_pretrained(MODEL_NAME).to(DEVICE)
    print("Model loaded successfully.")
except Exception as e:
    print(f"Error loading model: {e}")
    # モデルがロードできない場合、サーバーは起動しないようにします
    TOKENIZER = None
    MODEL = None

# --- FastAPIアプリケーションのインスタンス化 ---
app = FastAPI(
    title="Melody Flow API",
    description="リズム入力からメロディを生成するAIのAPIです。",
    version="0.1.0",
)

# --- APIリクエスト/レスポンスのデータモデル ---
class MelodyGenerationRequest(BaseModel):
    chord_progression: str
    style: str

class MelodyGenerationResponse(BaseModel):
    midi_data: str
    raw_output: str # デバッグ用にモデルの生出力も返す

# --- ヘルパー関数 ---
def generate_midi_from_model(prompt: str) -> str:
    """テキストプロンプトからMIDIデータを生成する関数"""
    if not MODEL or not TOKENIZER:
        raise RuntimeError("Model is not loaded. Cannot generate MIDI.")

    print("Generating MIDI data...")
    inputs = TOKENIZER(prompt, return_tensors="pt").to(DEVICE)
    
    # モデルにテキストを生成させる
    output = MODEL.generate(
        **inputs,
        max_new_tokens=256,
        temperature=0.75,
        pad_token_id=TOKENIZER.eos_token_id # open-end generationのための設定
    )
    
    # 生成されたトークンをデコードして、MIDI文字列に変換
    decoded_output = TOKENIZER.decode(output[0])
    print("Generation complete.")
    return decoded_output

def parse_and_encode_midi(decoded_text: str) -> str:
    """モデルの出力テキストからMIDIデータ部分を抽出し、Base64エンコードする"""
    # "pitch duration wait velocity instrument"ヘッダー以降の行を抽出
    match = re.search(r'pitch duration wait velocity instrument\s*\n(.*)', decoded_text, re.DOTALL)
    if match:
        midi_note_data = match.group(1).strip()
        print(f"Extracted MIDI notes:\n{midi_note_data[:100]}...") # 最初の100文字だけ表示
    else:
        # マッチしない場合は、とりあえず生テキスト全体を使う（フォールバック）
        print("Warning: Could not find MIDI header. Using full decoded text.")
        midi_note_data = decoded_text

    # Base64エンコード
    midi_binary = midi_note_data.encode('utf-8')
    midi_base64 = base64.b64encode(midi_binary).decode('utf-8')
    return midi_base64

# --- APIエンドポイント ---
@app.get("/")
def read_root():
    return {"message": "Welcome to Melody Flow AI API!"}

@app.post("/generate", response_model=MelodyGenerationResponse)
def generate_melody(request: MelodyGenerationRequest):
    """コード進行とスタイルを受け取り、メロディを生成する"""
    # 【変更点】プロンプトの末尾にヘッダーを追加し、メロディ生成を促します。
    prompt = f"style={request.style}, chord_progression={request.chord_progression}\npitch duration wait velocity instrument\n"
    print(f"Received request with prompt: {prompt}")

    # AIモデルを呼び出してMIDIデータを生成
    raw_model_output = generate_midi_from_model(prompt)
    
    # モデルの出力をパースしてBase64にエンコード
    midi_base64_data = parse_and_encode_midi(raw_model_output)

    return MelodyGenerationResponse(
        midi_data=midi_base64_data,
        raw_output=raw_model_output # デバッグ用に生データも返す
    )

# --- サーバーの起動 ---
if __name__ == "__main__":
    # uvicorn.runにFastAPIのインスタンス(app)を直接渡すことで、
    # ファイル名に依存しない、より堅牢な起動ができます。
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

