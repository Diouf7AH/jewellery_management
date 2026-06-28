from io import BytesIO

import qrcode
from PIL import Image, ImageDraw, ImageFont


def _center_text(draw, x1, x2, y, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = x1 + ((x2 - x1 - text_width) // 2)
    draw.text((x, y), text, fill="black", font=font)


def build_etiquette_bague_png(produit):
    # 30 mm x 25 mm à 203 DPI ≈ 240 x 200 px
    width = 240
    height = 200

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("arial.ttf", 22)
        font_big = ImageFont.truetype("arial.ttf", 36)
        font_weight = ImageFont.truetype("arial.ttf", 30)
        font_small = ImageFont.truetype("arial.ttf", 13)
    except OSError:
        font_title = ImageFont.load_default()
        font_big = ImageFont.load_default()
        font_weight = ImageFont.load_default()
        font_small = ImageFont.load_default()

    sku = produit.sku or f"P-{produit.id}"
    qr_content = sku

    purete = str(produit.purete) if produit.purete else ""
    poids = f"{produit.poids} g" if produit.poids else ""

    reference = sku[:18]

    # # Séparation gauche/droite
    # left_w = 82
    # right_x1 = 90
    # right_x2 = width - 5

    # draw.line((86, 18, 86, height - 18), fill="black", width=1)
    
    # # Séparation gauche/droite
    left_w = 80
    right_x1 = 85
    right_x2 = width - 5

    # QR à gauche, plus petit
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=3,
        border=1,
    )
    qr.add_data(qr_content)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    # qr_img = qr_img.resize((58, 58))
    # img.paste(qr_img, (12, 45))
    qr_img = qr_img.resize((55, 55))
    img.paste(qr_img, (12, 55))

    # SKU court à gauche
    # _center_text(draw, 2, left_w, 112, reference[:10], font_small)
    _center_text(draw, 2, left_w, 118, reference[:10], font_small)
    if len(reference) > 10:
        _center_text(draw, 2, left_w, 128, reference[10:18], font_small)

    # Infos à droite
    _center_text(draw, right_x1, right_x2, 12, "RIO GOLD", font_title)
    _center_text(draw, right_x1, right_x2, 55, purete, font_big)
    _center_text(draw, right_x1, right_x2, 118, poids, font_weight)

    output = BytesIO()
    img.save(output, format="PNG")
    output.seek(0)

    return output

