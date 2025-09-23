import unsloth  # noqa: F401
import base64
import os
import re
import time

from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from src.model.melody_processor import MelodyControlLogitsProcessor, NoteTokenizer
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, LogitsProcessorList
from unsloth import FastLanguageModel
import uvicorn

# --- 環境変数に応じてWeaveの有効/無効を切り替える ---
APP_ENV = os.getenv("APP_ENV", "production")  # デフォルトは安全な 'production'

if APP_ENV != "production":
    print("🚀 Running in DEVELOPMENT mode. Weave is enabled.")
    try:
        import weave

        weave.init("melody-flow-api-dev")
        op = weave.op  # 開発モードでは実際のweave.opを使用
    except ImportError:
        print("⚠️  weave is not installed. Running without it.")

        # weaveがない場合は何もしないダミーデコレータを定義
        def op(*args, **kwargs):
            def decorator(f):
                return f

            if args and callable(args[0]):
                return decorator(args[0])
            return decorator

else:
    print("✅ Running in PRODUCTION mode. Weave is disabled.")

    # 本番モードでは何もしないダミーデコレータを定義
    def op(*args, **kwargs):
        def decorator(f):
            return f

        # @op と @op() の両方の構文に対応
        if args and callable(args[0]):
            return decorator(args[0])
        return decorator


# --- モデル読み込み (変更なし) ---
MODEL_NAME = os.getenv("MODEL_NAME", "models/production.pth/")
print(f"🧠 Loading model: {MODEL_NAME}...")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"🔥 Using device: {DEVICE}")

try:
    MODEL, TOKENIZER = None, None
    if os.path.isdir(MODEL_NAME):
        print("-> Loading as local Unsloth model (4-bit)...")
        MODEL, TOKENIZER = FastLanguageModel.from_pretrained(
            model_name=MODEL_NAME, max_seq_length=4096, dtype=None, load_in_4bit=True
        )
    else:
        print(f"-> Loading as Hugging Face Hub model ({MODEL_NAME})...")
        MODEL = AutoModelForCausalLM.from_pretrained(MODEL_NAME, torch_dtype=torch.bfloat16).to(
            DEVICE
        )
        TOKENIZER = AutoTokenizer.from_pretrained(MODEL_NAME)

    NOTE_TOKENIZER_HELPER = NoteTokenizer(TOKENIZER)
    print("✅ Model loaded successfully.")
except Exception as e:
    print(f"❌ Fatal: Error loading model: {e}")
    MODEL, TOKENIZER, NOTE_TOKENIZER_HELPER = None, None, None

app = FastAPI(title="Melody Flow Local API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Weaveのデコレータを条件付きで適用 ---
@op()  # APP_ENVに応じて本物のデコレータかダミーが使われる
def generate_midi_from_model(
    prompt: str, processor: MelodyControlLogitsProcessor, seed: int
) -> str:
    if not MODEL or not TOKENIZER:
        raise RuntimeError("Model is not loaded.")
    torch.manual_seed(seed)
    inputs = TOKENIZER(prompt, return_tensors="pt").to(DEVICE)
    logits_processors = LogitsProcessorList([processor])
    output = MODEL.generate(
        **inputs,
        max_new_tokens=128,
        temperature=0.75,
        pad_token_id=TOKENIZER.eos_token_id,
        logits_processor=logits_processors,
    )
    # 開発モードの時だけWeaveに情報を記録
    if APP_ENV != "production" and "weave" in globals():
        weave.summary(
            {"allowed_notes": processor.note_tokenizer.ids_to_string(processor.allowed_token_ids)}
        )
    return TOKENIZER.decode(output[0])


def parse_and_encode_midi(decoded_text: str) -> str:
    match = re.search(r"pitch duration wait velocity instrument\s*\n(.*)", decoded_text, re.DOTALL)
    midi_note_data = match.group(1).strip() if match else decoded_text
    return base64.b64encode(midi_note_data.encode("utf-8")).decode("utf-8")


@op()  # APP_ENVに応じて本物のデコレータかダミーが使われる
@app.get("/generate")
def generate_melody(
    response: Response,
    chord_progression: str = Query(..., description="コード進行"),
    style: str = Query(..., description="音楽スタイル"),
    variation: int = Query(1, description="バリエーション（乱数シード）"),
):
    start_time = time.time()
    chords = [chord.strip() for chord in chord_progression.split("-")]
    melodies = {}

    for chord in chords:
        processor = MelodyControlLogitsProcessor(chord, NOTE_TOKENIZER_HELPER)
        prompt = (
            f"style={style}, chord_progression={chord}\npitch duration wait velocity instrument\n"
        )
        raw_output = generate_midi_from_model(prompt, processor, seed=variation)
        encoded_midi = parse_and_encode_midi(raw_output)

        key = chord
        count = 2
        while key in melodies:
            key = f"{chord}_{count}"
            count += 1
        melodies[key] = encoded_midi

    print(f"Generated melody in {time.time() - start_time:.2f} seconds for variation {variation}")
    return {"chord_melodies": melodies}


current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, "..", "..", "static")

app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=FileResponse)
async def read_index():
    return FileResponse(os.path.join(static_dir, "index.html"))


def start():
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    start()
