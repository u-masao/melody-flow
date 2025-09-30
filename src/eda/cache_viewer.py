import json
from fastapi import Response
import streamlit as st
import hashlib
import itertools
import os
from pathlib import Path
import sys
from dotenv import load_dotenv
from loguru import logger
from tqdm import tqdm
import wandb

sys.path.append(str(Path(__file__).resolve().parents[2]))
load_dotenv()

from src.api.main import generate_melody  # noqa: E402
from src.warmup.generate_static_cache import (  # noqa: E402
    get_chord_progressions_from_html,
    transpose_progression,
)
import src.warmup.generate_static_cache as conf  # noqa: E402
from src.model.visualize import plot_melodies  # noqa: E402


# デフォルトのハンドラを削除
logger.remove()
# 標準出力にINFOレベル以上を出力するハンドラを追加
logger.add(sys.stdout, level="INFO")

run = wandb.init(entity=os.environ["WANDB_ENTITY"], project=os.environ["WANDB_PROJECT"])


# --- メイン処理 ---
def main(
    supress_token_prob_ratio: float = 0.3,
    instrument: str = "Alto Saxophone",
):
    # APP HTML からコード進行を読み込む
    chord_progressions = get_chord_progressions_from_html(conf.APP_HTML_PATH)
    if not chord_progressions:
        logger.info("Aborting: No chord progressions found.")
        return

    # 全ての組み合わせを作成
    logger.info("🚀 Starting static cache generation for all keys...")
    variations = [x + 1 for x in range(10)]
    styles = ["JAZZ風"]
    all_combinations = list(
        itertools.product([chord_progressions[0]], [conf.ALL_KEYS[0]], styles, variations)
    )

    with tqdm(all_combinations, desc="Generating Cache", unit="file") as pbar:
        for prog_info, target_key, style, var in pbar:
            # 変数を作成
            original_prog = prog_info["progression"]
            original_key = prog_info["original_key"]
            transposed_prog = transpose_progression(original_prog, original_key, target_key)
            st.write(transposed_prog)
            prog_hash = hashlib.md5(transposed_prog.encode()).hexdigest()

            # プログレスバーを更新
            pbar.set_description(f"Hash: {prog_hash}, Style: {style}, Variation: {var}")

            # ファイル名を作成
            output_path = conf.OUTPUT_DIR / prog_hash / style
            os.makedirs(output_path, exist_ok=True)
            output_file = output_path / f"{var}.json"

            # メロディを生成(API 呼び出し)
            response = generate_melody(
                Response,
                chord_progression=transposed_prog,
                style=style,
                variation=var,
                supress_token_prob_ratio=supress_token_prob_ratio,
                instrument=instrument,
            )
            st.write(plot_melodies(response))

            # ファイル存在チェック
            if os.path.exists(output_file):
                st.write(output_file)
                with open(output_file) as fo:
                    cache = json.load(fo)
                st.write(plot_melodies(cache))

    logger.info("🎉 Static cache generation finished!")


if __name__ == "__main__":
    main()
