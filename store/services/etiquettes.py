from io import BytesIO

import qrcode
from PIL import Image, ImageDraw, ImageFont


def _center_text(draw, x1, x2, y, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    draw.text(
        (x1 + ((x2 - x1 - w) // 2), y),
        text,
        fill="black",
        font=font,
    )


def build_etiquette_bague_png(produit):

    # ==========================================================
    # Etiquette 35 x 30 mm (≈280 x 240 px à 203 dpi)
    # ==========================================================

    width = 280
    height = 240

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    try:
        FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

        font_title = ImageFont.truetype(FONT, 24)
        font_purete = ImageFont.truetype(FONT, 48)
        font_poids = ImageFont.truetype(FONT, 38)
        font_ref = ImageFont.truetype(FONT, 16)

    except Exception:
        font_title = ImageFont.load_default()
        font_purete = ImageFont.load_default()
        font_poids = ImageFont.load_default()
        font_ref = ImageFont.load_default()

    # ==========================================================
    # Données
    # ==========================================================

    purete = str(produit.purete) if produit.purete else ""
    poids = f"{produit.poids} g" if produit.poids else ""

    qr_content = produit.sku

    reference = (
        f"{(produit.categorie.nom if produit.categorie else '')[:3].upper()}-"
        f"{(produit.modele.modele if produit.modele else '')[:3].upper()}-"
        f"{produit.etat}-"
        f"{(produit.marque.marque if produit.marque else '')[:3].upper()}"
    )

    # ==========================================================
    # Mise en page
    # ==========================================================

    marge = 16          # ≈2 mm
    espace = 32         # ≈4 mm

    colonne_gauche = 100

    left_x1 = marge
    left_x2 = marge + colonne_gauche

    right_x1 = left_x2 + espace
    right_x2 = width - marge

    # ==========================================================
    # QR Code
    # ==========================================================

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=4,
        border=1,
    )

    qr.add_data(qr_content)
    qr.make(fit=True)

    qr_img = (
        qr.make_image(
            fill_color="black",
            back_color="white",
        )
        .convert("RGB")
        .resize((70, 70))
    )

    qr_x = left_x1 + ((colonne_gauche - 70) // 2)

    img.paste(
        qr_img,
        (
            qr_x,
            35,
        ),
    )

    # ==========================================================
    # Référence
    # ==========================================================

    _center_text(
        draw,
        left_x1,
        left_x2,
        118,
        reference,
        font_ref,
    )

    # ==========================================================
    # RIO GOLD
    # ==========================================================

    _center_text(
        draw,
        right_x1,
        right_x2,
        12,
        "RIO GOLD",
        font_title,
    )

    # ==========================================================
    # Pureté
    # ==========================================================

    _center_text(
        draw,
        right_x1,
        right_x2,
        55,
        purete,
        font_purete,
    )

    # ==========================================================
    # Poids
    # ==========================================================

    _center_text(
        draw,
        right_x1,
        right_x2,
        135,
        poids,
        font_poids,
    )

    # ==========================================================
    output = BytesIO()

    img.save(
        output,
        format="PNG",
    )

    output.seek(0)

    return output

