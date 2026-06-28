from io import BytesIO

import qrcode
from PIL import Image, ImageDraw, ImageFont


def _center_text(draw, x1, x2, y, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = x1 + ((x2 - x1 - text_width) // 2)
    draw.text((x, y), text, fill="black", font=font)


def build_etiquette_bague_png(produit):
    # 35 mm x 30 mm à 203 DPI ≈ 280 x 240 px
    width = 280
    height = 240

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    try:
        FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

        font_title = ImageFont.truetype(FONT, 24)
        font_purete = ImageFont.truetype(FONT, 40)
        font_poids = ImageFont.truetype(FONT, 34)
        font_sku_label = ImageFont.truetype(FONT, 14)
        font_ref = ImageFont.truetype(FONT, 18)

    except Exception:
        font_title = ImageFont.load_default()
        font_purete = ImageFont.load_default()
        font_poids = ImageFont.load_default()
        font_sku_label = ImageFont.load_default()
        font_ref = ImageFont.load_default()

    sku = produit.sku or f"P-{produit.id}"
    qr_content = sku

    purete = str(produit.purete) if produit.purete else ""
    poids = f"{produit.poids} g" if produit.poids else ""

    reference = (
        f"{(produit.categorie.nom if produit.categorie else '')[:3].upper()}-"
        f"{(produit.modele.modele if produit.modele else '')[:3].upper()}-"
        f"{produit.etat}-"
        f"{(produit.marque.marque if produit.marque else '')[:3].upper()}"
    )

    # Marges : 2 mm ≈ 16 px ; espace entre colonnes : 4 mm ≈ 32 px
    margin = 16
    gap = 32

    left_x1 = margin
    left_x2 = 130

    right_x1 = left_x2 + gap
    right_x2 = width - margin

    # QR code à gauche
    qr_size = 92
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=4,
        border=1,
    )
    qr.add_data(qr_content)
    qr.make(fit=True)

    qr_img = qr.make_image(
        fill_color="black",
        back_color="white",
    ).convert("RGB")

    qr_img = qr_img.resize((qr_size, qr_size))

    qr_x = left_x1 + ((left_x2 - left_x1 - qr_size) // 2)
    img.paste(qr_img, (qr_x, 38))

    # SKU court à gauche
    _center_text(draw, left_x1, left_x2, 140, "SKU", font_sku_label)
    _center_text(draw, left_x1, left_x2, 160, reference, font_ref)

    # Infos à droite
    _center_text(draw, right_x1, right_x2, 30, "RIO GOLD", font_title)
    _center_text(draw, right_x1, right_x2, 85, purete, font_purete)
    _center_text(draw, right_x1, right_x2, 150, poids, font_poids)

    output = BytesIO()
    img.save(output, format="PNG")
    output.seek(0)

    return output

