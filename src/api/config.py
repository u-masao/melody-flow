import os
import torch

# モデル設定
MODEL_NAME = os.getenv("MODEL_NAME", "models/llama-midi.pth/")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# API設定
API_TITLE = "Melody Flow API"
CORS_ORIGINS = [
    "https://melody-flow.click",
    "http://localhost:7860",
    "http://127.0.0.1:7860",
]
STATIC_FILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "static")
INDEX_HTML_PATH = os.path.join(STATIC_FILES_DIR, "index.html")

# 生成パラメータ
DEFAULT_MAX_NEW_TOKENS = 128
DEFAULT_TEMPERATURE = 0.75
