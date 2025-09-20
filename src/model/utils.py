import unsloth  # noqa: F401
import os
import sys

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, LogitsProcessorList
from unsloth import FastLanguageModel

from src.model.melody_processor import NoteTokenizer

def _get_op_decorator():
    """環境変数に応じて、weave.opまたは何もしないダミーデコレータを返す"""
    if os.getenv("APP_ENV", "production") != "production":
        try:
            import weave
            return weave.op
        except ImportError:
            print("⚠️  weave is not installed. Running without it.")

    # 本番モード、またはweaveがインストールされていない場合はダミーを返す
    def dummy_op(*args, **kwargs):
        def decorator(f):
            return f
        if args and callable(args[0]):
            return decorator(args[0])
        return decorator
    return dummy_op

# --- グローバル変数としてデコレータを定義 ---
op = _get_op_decorator()
APP_ENV = os.getenv("APP_ENV", "production")


def load_model_and_tokenizer(model_path: str | None):
    """
    モデルとトークナイザーをパスから読み込みます。
    ローカルパスの場合はUnslothを、Hubのパスの場合はTransformersを使用します。
    """
    if model_path is None:
        model_path = "models/llama-midi.pth/"
    print(f"🧠 Loading model: {model_path}...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"🔥 Using device: {device}")

    try:
        model, tokenizer = None, None
        if os.path.isdir(model_path):
            print("-> Loading as local Unsloth model (4-bit)...")
            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name=model_path, max_seq_length=4096, dtype=None, load_in_4bit=True
            )
        else:
            print(f"-> Loading as Hugging Face Hub model ({model_path})...")
            model = AutoModelForCausalLM.from_pretrained(
                model_path, torch_dtype=torch.bfloat16
            ).to(device)
            tokenizer = AutoTokenizer.from_pretrained(model_path)

        note_tokenizer_helper = NoteTokenizer(tokenizer)
        print("✅ Model loaded successfully.")
        return model, tokenizer, note_tokenizer_helper, device
    except Exception as e:
        print(f"❌ Fatal: Error loading model: {e}")
        return None, None, None, None


@op()
def generate_midi_from_model(
    model, tokenizer, device, prompt: str, processor, seed: int
) -> str:
    """
    プロンプトとLogitsProcessorを使用してMIDIテキストを生成します。
    """
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
    if APP_ENV != "production":
        # 'weave'がインポートされている場合のみ実行
        try:
            import weave
            weave.summary({"allowed_notes": processor.note_tokenizer.ids_to_string(processor.allowed_token_ids)})
        except ImportError:
            pass # weaveがなければ何もしない
    return tokenizer.decode(output[0])


