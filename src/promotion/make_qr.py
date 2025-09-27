import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask
from PIL import Image, ImageDraw
import cairosvg
import io

# --- 設定項目 ---
QR_DATA = "https://melody-flow.click"
OUTPUT_FILENAME = "docs/slide_qr_code.png"
DOT_COLOR = (147, 112, 219) # "#9370db"
QR_BG_COLOR = (229, 231, 235)  # "#e5e7eb"
SLIDE_BG_COLOR = "#111827"
CANVAS_SIZE = 800
SVG_DATA = """
<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
    <defs>
        <linearGradient id="faviconGradient" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#818cf8"/>
            <stop offset="100%" stop-color="#c084fc"/>
        </linearGradient>
    </defs>
    <rect x="0" y="0" width="100" height="100" rx="20" fill="#e5e7eb"/>
    <path d="M20 70 C 35 90, 65 90, 80 70" stroke="url(#faviconGradient)"
        stroke-width="10" fill="none" stroke-linecap="round"/>
    <path d="M30 50 C 40 65, 60 65, 70 50" stroke="url(#faviconGradient)"
        stroke-width="10" fill="none" stroke-linecap="round"/>
    <path d="M40 30 C 45 40, 55 40, 60 30" stroke="url(#faviconGradient)"
        stroke-width="10" fill="none" stroke-linecap="round"/>
</svg>
"""

# --- ここから下は通常変更不要です ---


def create_slide_qr_code():
    """スライド埋め込み用の円形QRコード画像を生成します。"""

    # キャンバスよりも一回り小さい円の直径を計算
    qr_code_display_size = int(CANVAS_SIZE * 0.95)

    # QRコードを生成。背景色を円の色と同じにする
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, border=8)
    qr.add_data(QR_DATA)
    qr_img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=RoundedModuleDrawer(radius_ratio=0.9),
        color_mask=SolidFillColorMask(front_color=DOT_COLOR, back_color=QR_BG_COLOR),
    )

    # SVGロゴをQRコードに合成
    qr_width, qr_height = qr_img.size
    logo_max_size = int(qr_width * 0.15)
    png_data = cairosvg.svg2png(
        bytestring=SVG_DATA.encode("utf-8"),
        output_width=logo_max_size,
        output_height=logo_max_size,
    )
    logo_img = Image.open(io.BytesIO(png_data))
    pos = ((qr_width - logo_img.size[0]) // 2, (qr_height - logo_img.size[1]) // 2)
    qr_img.paste(logo_img, pos, logo_img)

    # 貼り付け先の暗い背景キャンバスを作成
    canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), SLIDE_BG_COLOR)
    mask = Image.new("L", (qr_code_display_size, qr_code_display_size), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse((0, 0, qr_code_display_size, qr_code_display_size), fill=255)

    # QRコード画像を円のサイズに合わせてリサイズ
    qr_img_resized = qr_img.resize(
        (qr_code_display_size, qr_code_display_size), Image.Resampling.LANCZOS
    )

    # キャンバスの中央に、円形マスクを使ってQRコードを貼り付け
    paste_x = (CANVAS_SIZE - qr_code_display_size) // 2
    paste_y = (CANVAS_SIZE - qr_code_display_size) // 2
    canvas.paste(qr_img_resized, (paste_x, paste_y), mask)

    # 最終画像を保存
    canvas.save(OUTPUT_FILENAME)
    print(f"saved: {OUTPUT_FILENAME}")


if __name__ == "__main__":
    create_slide_qr_code()
