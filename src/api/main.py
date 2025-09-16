import base64
import os
import re
import time
from contextlib import asynccontextmanager

import torch
import uvicorn
from fastapi import FastAPI, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    LogitsProcessorList,
    PreTrainedModel,
    PreTrainedTokenizer,
)

# Unsloth is imported for its side-effects and potential optimizations
try:
    import unsloth  # noqa: F401
    from unsloth import FastLanguageModel
except (ImportError, NotImplementedError):
    # Handle environments where unsloth is not installed or not supported
    FastLanguageModel = AutoModelForCausalLM

from src.model.melody_processor import MelodyControlLogitsProcessor, NoteTokenizer

# --- Global Configuration ---
MODEL_NAME = os.getenv("MODEL_NAME", "models/llama-midi.pth/")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"🔥 Using device: {DEVICE}")


# --- Model Loading Logic ---
def load_model():
    """Loads the appropriate model and tokenizer based on the MODEL_NAME."""
    print(f"🧠 Loading model: {MODEL_NAME}...")
    model, tokenizer = None, None
    try:
        if os.path.isdir(MODEL_NAME) and FastLanguageModel is not AutoModelForCausalLM:
            print("-> Loading as local Unsloth model (4-bit)...")
            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name=MODEL_NAME, max_seq_length=4096, dtype=None, load_in_4bit=True
            )
        else:
            print(f"-> Loading as Hugging Face Hub model ({MODEL_NAME})...")
            model = AutoModelForCausalLM.from_pretrained(
                MODEL_NAME, torch_dtype=torch.bfloat16
            ).to(DEVICE)
            tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

        note_tokenizer_helper = NoteTokenizer(tokenizer)
        print("✅ Model loaded successfully.")
        return model, tokenizer, note_tokenizer_helper
    except Exception as e:
        print(f"❌ Fatal: Error loading model: {e}")
        return None, None, None


# --- FastAPI Lifespan Management ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the model on startup and store it in the app state."""
    model, tokenizer, note_tokenizer_helper = load_model()
    app.state.model = model
    app.state.tokenizer = tokenizer
    app.state.note_tokenizer_helper = note_tokenizer_helper
    yield
    # Clean up resources if needed on shutdown
    app.state.model = None
    app.state.tokenizer = None
    app.state.note_tokenizer_helper = None


app = FastAPI(title="Melody Flow Local API", lifespan=lifespan)

# --- Dependency Injection ---
class ModelDependencies:
    def __init__(self, model: PreTrainedModel, tokenizer: PreTrainedTokenizer, note_helper: NoteTokenizer):
        self.model = model
        self.tokenizer = tokenizer
        self.note_helper = note_helper

def get_model_dependencies(request: "Request") -> ModelDependencies:
    if not request.app.state.model or not request.app.state.tokenizer:
        raise RuntimeError("Model is not loaded or failed to load.")
    return ModelDependencies(
        model=request.app.state.model,
        tokenizer=request.app.state.tokenizer,
        note_helper=request.app.state.note_tokenizer_helper
    )

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Core Generation Logic ---
def generate_midi_from_model(
    prompt: str,
    processor: MelodyControlLogitsProcessor,
    seed: int,
    deps: ModelDependencies,
) -> str:
    torch.manual_seed(seed)
    inputs = deps.tokenizer(prompt, return_tensors="pt").to(DEVICE)
    logits_processors = LogitsProcessorList([processor])
    output = deps.model.generate(
        **inputs,
        max_new_tokens=128,
        temperature=0.75,
        pad_token_id=deps.tokenizer.eos_token_id,
        logits_processor=logits_processors,
    )
    return deps.tokenizer.decode(output[0])


def parse_and_encode_midi(decoded_text: str) -> str:
    match = re.search(r"pitch duration wait velocity instrument\s*\n(.*)", decoded_text, re.DOTALL)
    midi_note_data = match.group(1).strip() if match else decoded_text
    return base64.b64encode(midi_note_data.encode("utf-8")).decode("utf-8")


# --- API Endpoints ---
@app.get("/generate")
def generate_melody(
    chord_progression: str = Query(..., description="コード進行"),
    style: str = Query(..., description="音楽スタイル"),
    variation: int = Query(1, description="バリエーション（乱数シード）"),
    model_deps: ModelDependencies = Depends(get_model_dependencies),
):
    start_time = time.time()
    chords = [chord.strip() for chord in chord_progression.split("-")]
    melodies = {}

    for chord in chords:
        processor = MelodyControlLogitsProcessor(chord, model_deps.note_helper)
        prompt = (
            f"style={style}, chord_progression={chord}\npitch duration wait velocity instrument\n"
        )
        raw_output = generate_midi_from_model(prompt, processor, seed=variation, deps=model_deps)
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
