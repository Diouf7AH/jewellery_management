from io import BytesIO

import qrcode
from PIL import Image, ImageDraw, ImageFont


def _center_text(draw, x1, x2, y, text, font):
    text = str(text or "")
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
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        font_title = ImageFont.truetype(font_path, 20)
        font_label = ImageFont.truetype(font_path, 15)
        font_purete = ImageFont.truetype(font_path, 38)
        font_poids = ImageFont.truetype(font_path, 30)
        font_ref = ImageFont.truetype(font_path, 18)
    except Exception:
        font_title = ImageFont.load_default()
        font_label = ImageFont.load_default()
        font_purete = ImageFont.load_default()
        font_poids = ImageFont.load_default()
        font_ref = ImageFont.load_default()

    qr_content = f"P:{produit.uuid}" if produit.uuid else f"P:{produit.id}"

    purete = str(produit.purete) if produit.purete else ""
    poids = f"{produit.poids} g" if produit.poids else ""

    reference = (
        f"{(produit.categorie.nom if produit.categorie else '')[:3].upper()}-"
        f"{(produit.modele.modele if produit.modele else '')[:3].upper()}-"
        f"{produit.etat or ''}-"
        f"{(produit.marque.marque if produit.marque else '')[:3].upper()}"
    )

    parts = reference.split("-", 2)
    if len(parts) == 3:
        sku_line_1 = f"{parts[0]} {parts[1]}"
        sku_line_2 = parts[2].replace("-", " ")
    else:
        mid = len(reference) // 2
        sku_line_1 = reference[:mid]
        sku_line_2 = reference[mid:]

    margin_outer = 20

    # Zone gauche
    left_x1 = margin_outer
    left_x2 = 120

    qr_size = 88
    qr_x = left_x1 + ((left_x2 - left_x1 - qr_size) // 2)
    qr_y = 15

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(qr_content)
    qr.make(fit=True)

    qr_img = qr.make_image(
        fill_color="black",
        back_color="white",
    ).convert("RGB")

    qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.NEAREST)
    img.paste(qr_img, (qr_x, qr_y))

    # SKU court sous le QR, sans carré
    _center_text(draw, left_x1, left_x2, 118, sku_line_1, font_ref)
    _center_text(draw, left_x1, left_x2, 145, sku_line_2, font_ref)

    # Zone droite
    right_x1 = 120
    right_x2 = width - margin_outer

    _center_text(draw, right_x1, right_x2, 25, "RIO GOLD", font_title)
    _center_text(draw, right_x1, right_x2, 65, "PURETÉ", font_label)
    _center_text(draw, right_x1, right_x2, 88, purete, font_purete)
    _center_text(draw, right_x1, right_x2, 140, "POIDS", font_label)
    _center_text(draw, right_x1, right_x2, 160, poids, font_poids)

    output = BytesIO()
    img.save(output, format="PNG")
    output.seek(0)

    return output

