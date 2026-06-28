from io import BytesIO

import qrcode
from PIL import Image, ImageDraw, ImageFont


def _center_text(draw, x1, x2, y, text, font):
    bbox = draw.textbbox((0, 0), str(text), font=font)
    w = bbox[2] - bbox[0]
    x = x1 + ((x2 - x1 - w) // 2)
    draw.text((x, y), str(text), fill="black", font=font)


def build_etiquette_bague_png(produit):
    # 30 x 25 mm @203 dpi
    WIDTH = 240
    HEIGHT = 200

    img = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(img)

    try:
        FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

        font_title = ImageFont.truetype(FONT, 20)
        font_label = ImageFont.truetype(FONT, 15)
        font_purete = ImageFont.truetype(FONT, 38)
        font_poids = ImageFont.truetype(FONT, 28)
        font_ref = ImageFont.truetype(FONT, 15)

    except Exception:
        font_title = ImageFont.load_default()
        font_label = ImageFont.load_default()
        font_purete = ImageFont.load_default()
        font_poids = ImageFont.load_default()
        font_ref = ImageFont.load_default()

    qr_content = f"P:{produit.uuid}"

    purete = str(produit.purete or "")
    poids = f"{produit.poids} g" if produit.poids else ""

    reference = (
        f"{(produit.categorie.nom if produit.categorie else '')[:3].upper()}-"
        f"{(produit.modele.modele if produit.modele else '')[:3].upper()}-"
        f"{(produit.etat or '')}-"
        f"{(produit.marque.marque if produit.marque else '')[:3].upper()}"
    )

    # BAG-MOD-
    # N-RIO
    p = reference.split("-", 2)

    if len(p) == 3:
        ref1 = f"{p[0]}-{p[1]}-"
        ref2 = p[2]
    else:
        ref1 = reference
        ref2 = ""

    # -----------------------------
    # QR CODE
    # -----------------------------

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

    qr_size = 90

    qr_img = qr_img.resize(
        (qr_size, qr_size),
        Image.Resampling.NEAREST,
    )

    qr_x = 15
    qr_y = 12

    img.paste(qr_img, (qr_x, qr_y))

    # -----------------------------
    # SKU
    # -----------------------------

    _center_text(
        draw,
        10,
        120,
        110,
        ref1,
        font_ref,
    )

    _center_text(
        draw,
        10,
        120,
        130,
        ref2,
        font_ref,
    )

    # -----------------------------
    # Partie droite
    # -----------------------------

    right_x1 = 120
    right_x2 = WIDTH - 10

    _center_text(
        draw,
        right_x1,
        right_x2,
        18,
        "RIO GOLD",
        font_title,
    )

    _center_text(
        draw,
        right_x1,
        right_x2,
        55,
        "PURETÉ",
        font_label,
    )

    _center_text(
        draw,
        right_x1,
        right_x2,
        73,
        purete,
        font_purete,
    )

    _center_text(
        draw,
        right_x1,
        right_x2,
        132,
        "POIDS",
        font_label,
    )

    _center_text(
        draw,
        right_x1,
        right_x2,
        150,
        poids,
        font_poids,
    )

    output = BytesIO()
    img.save(output, "PNG")
    output.seek(0)

    return output

