import sys
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel
import uvicorn

from . import config
from .services import MelodyGenerationService, ModelManager

# --- ロガー設定 ---
logger.remove()
logger.add(sys.stdout, level="INFO")

# --- モデルとサービスの初期化 ---
logger.info("アプリケーションを初期化中...")
model_manager = ModelManager(model_name=config.MODEL_NAME, device=config.DEVICE)
melody_service = MelodyGenerationService(model_manager=model_manager)
logger.info("アプリケーションの初期化が完了しました。")


# --- FastAPIアプリの初期化 ---
app = FastAPI(title=config.API_TITLE)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=config.STATIC_FILES_DIR), name="static")


# --- APIモデル ---
class MelodyGenerationRequest(BaseModel):
    chord_progression: str
    style: str


class MelodyGenerationResponse(BaseModel):
    chord_melodies: dict[str, str]
    raw_outputs: dict[str, str]


# --- APIエンドポイント ---
@app.get("/", response_class=FileResponse)
async def read_index():
    """メインのindex.htmlファイルを提供します。"""
    return FileResponse(config.INDEX_HTML_PATH)


@app.post("/generate", response_model=MelodyGenerationResponse)
def generate_melody(request: MelodyGenerationRequest):
    """
    コード進行とスタイルに基づいてメロディを生成します。
    """
    if not model_manager.is_ready():
        logger.error("モデルが利用できません。生成リクエストを処理できません。")
        raise HTTPException(status_code=503, detail="モデルがロードされていないか、準備ができていません。")

    try:
        melodies, raw_outputs = melody_service.generate_melodies_for_chords(
            chord_progression=request.chord_progression, style=request.style
        )
        return MelodyGenerationResponse(chord_melodies=melodies, raw_outputs=raw_outputs)
    except Exception as e:
        logger.exception("メロディ生成中に予期せぬエラーが発生しました。")
        raise HTTPException(status_code=500, detail=f"内部エラーが発生しました: {e}")


if __name__ == "__main__":
    logger.info("Uvicornサーバーを起動中...")
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
