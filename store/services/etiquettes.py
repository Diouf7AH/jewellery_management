from io import BytesIO

import qrcode
from PIL import Image, ImageDraw, ImageFont


def build_etiquette_bague_png(produit):
    # 30 mm × 25 mm à 203 DPI
    width = 240
    height = 200

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    # Police
    try:
        font_title = ImageFont.truetype("arial.ttf", 20)
        font_text = ImageFont.truetype("arial.ttf", 16)
    except OSError:
        font_title = ImageFont.load_default()
        font_text = ImageFont.load_default()

    purete = str(produit.purete) if produit.purete else ""
    poids = f"{produit.poids} g" if produit.poids else ""

    # QR Code (identifiant technique)
    qr_content = f"P:{produit.uuid}"

    # Référence courte affichée sur l'étiquette
    reference = (
        f"{(produit.categorie.nom or '')[:3].upper()}-"
        f"{(produit.modele.modele or '')[:3].upper()}-"
        f"{produit.etat}-"
        f"{(produit.marque.marque or '')[:3].upper()}"
    )

    # ---------- RIO GOLD ----------
    bbox = draw.textbbox((0, 0), "RIO GOLD", font=font_title)
    text_width = bbox[2] - bbox[0]

    draw.text(
        ((width - text_width) // 2, 10),
        "RIO GOLD",
        fill="black",
        font=font_title,
    )

    # ---------- Référence ----------
    bbox = draw.textbbox((0, 0), reference, font=font_text)
    text_width = bbox[2] - bbox[0]

    draw.text(
        ((width - text_width) // 2, 40),
        reference,
        fill="black",
        font=font_text,
    )

    # ---------- Pureté ----------
    bbox = draw.textbbox((0, 0), purete, font=font_text)
    text_width = bbox[2] - bbox[0]

    draw.text(
        ((width - text_width) // 2, 65),
        purete,
        fill="black",
        font=font_text,
    )

    # ---------- Poids ----------
    bbox = draw.textbbox((0, 0), poids, font=font_text)
    text_width = bbox[2] - bbox[0]

    draw.text(
        ((width - text_width) // 2, 85),
        poids,
        fill="black",
        font=font_text,
    )

    # ---------- QR ----------
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
        .resize((80, 80))
    )

    img.paste(qr_img, ((width - 80) // 2, 105))

    output = BytesIO()
    img.save(output, format="PNG")
    output.seek(0)

    return output

