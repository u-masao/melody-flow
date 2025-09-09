import unsloth  # noqa: F401
import base64
import os
import re
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from src.model.melody_processor import MelodyControlLogitsProcessor, NoteTokenizer
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, LogitsProcessorList
from unsloth import FastLanguageModel
import uvicorn

MODEL_NAME = os.getenv("MODEL_NAME", "models/llama-midi.pth/")
print(f"Loading model: {MODEL_NAME}...")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {DEVICE}")

try:
    if os.path.isdir(MODEL_NAME):
        print("Loading local Unsloth model...")
        MODEL, TOKENIZER = FastLanguageModel.from_pretrained(
            model_name=MODEL_NAME,
            max_seq_length=4096,
            dtype=None,
            load_in_4bit=True,
        )
    else:
        print("Loading HuggingFace model...")
        MODEL = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            torch_dtype=torch.bfloat16,
        ).to(DEVICE)
        TOKENIZER = AutoTokenizer.from_pretrained(MODEL_NAME)

    NOTE_TOKENIZER_HELPER = NoteTokenizer(TOKENIZER)
    print("Model loaded successfully.")
except Exception as e:
    print(f"Error loading model: {e}")
    TOKENIZER, MODEL, NOTE_TOKENIZER_HELPER = None, None, None


app = FastAPI(title="Melody Flow API")


origins = [
    "https://melody-flow.click",
    "http://localhost:7860",
    "http://127.0.0.1:7860",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, "..", "..", "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


class MelodyGenerationRequest(BaseModel):
    chord_progression: str
    style: str


class MelodyGenerationResponse(BaseModel):
    chord_melodies: dict[str, str]
    raw_outputs: dict[str, str]


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
        logits_processor=logits_processors,
    )
    return TOKENIZER.decode(output[0])


def parse_and_encode_midi(decoded_text: str) -> str:
    match = re.search(r"pitch duration wait velocity instrument\s*\n(.*)", decoded_text, re.DOTALL)
    midi_note_data = match.group(1).strip() if match else decoded_text
    return base64.b64encode(midi_note_data.encode("utf-8")).decode("utf-8")


@app.get("/", response_class=FileResponse)
async def read_index():
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.post("/generate", response_model=MelodyGenerationResponse)
def generate_melody(request: MelodyGenerationRequest):
    total_start_time = time.time()
    chords = [chord.strip() for chord in request.chord_progression.split("-")]
    melodies = {}
    raw_outputs = {}
    print(f"Generating melodies for chords: {chords}")
    for chord in chords:
        chord_start_time = time.time()
        processor = MelodyControlLogitsProcessor(chord, NOTE_TOKENIZER_HELPER)
        prompt = (
            f"style={request.style}, chord_progression={chord}\n"
            "pitch duration wait velocity instrument\n"
        )
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


if __name__ == "__main__":
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
