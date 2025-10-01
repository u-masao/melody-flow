import streamlit as st
from pathlib import Path
from PIL import Image
import numpy as np


def load_png(file_path: Path):
    original_image = Image.open(file_path)
    img_array = np.array(original_image.convert("RGBA"))
    rgb = 1.0 - img_array[:, :, :3] / 255.0

    min_out = 30
    max_out = 250
    range_width = max_out - min_out
    scaled = rgb * range_width + min_out
    return Image.fromarray(scaled.astype(np.uint8))


def main():
    st.header("キャッシュビューワ")
    dist_dir = Path("dist")
    for hash_dir in dist_dir.glob("*/*"):
        st.write(hash_dir)
        files = hash_dir.glob("**/*.png")
        cols = st.columns(len(list(files)))
        files = hash_dir.glob("**/*.png")
        for col, png_file in zip(cols, files, strict=False):
            with col:
                st.image(load_png(png_file))


if __name__ == "__main__":
    main()
