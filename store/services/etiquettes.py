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
        FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

        font_title = ImageFont.truetype(FONT, 20)
        font_label = ImageFont.truetype(FONT, 15)
        font_purete = ImageFont.truetype(FONT, 38)
        font_poids = ImageFont.truetype(FONT, 30)
        font_ref = ImageFont.truetype(FONT, 16)

    except Exception:
        font_title = ImageFont.load_default()
        font_label = ImageFont.load_default()
        font_purete = ImageFont.load_default()
        font_poids = ImageFont.load_default()
        font_ref = ImageFont.load_default()

    # QR = UUID produit
    qr_content = f"P:{produit.uuid}"

    purete = str(produit.purete) if produit.purete else ""
    poids = f"{produit.poids} g" if produit.poids else ""

    # SKU court affiché
    reference = (
        f"{(produit.categorie.nom if produit.categorie else '')[:3].upper()}-"
        f"{(produit.modele.modele if produit.modele else '')[:3].upper()}-"
        f"{produit.etat or ''}-"
        f"{(produit.marque.marque if produit.marque else '')[:3].upper()}"
    )

    # 1 mm ≈ 8 px à 203 DPI
    margin_outer = 20   # 2.5 mm
    margin_inner = 12   # 1.5 mm

    # Zone gauche : 15 mm ≈ 120 px
    left_x1 = margin_outer
    left_x2 = 120 - margin_outer

    # QR avec marge gauche/droite 2.5 mm
    qr_size = left_x2 - left_x1  # 80 px
    qr_x = left_x1
    qr_y = margin_outer

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
    img.paste(qr_img, (qr_x, qr_y))

    # SKU sous QR
    sku_box_x1 = margin_outer
    sku_box_x2 = 120 - margin_outer
    sku_box_y1 = qr_y + qr_size + 12
    sku_box_y2 = height - margin_outer

    draw.rectangle(
        (sku_box_x1, sku_box_y1, sku_box_x2, sku_box_y2),
        outline="black",
        width=1,
    )

    _center_text(
        draw,
        sku_box_x1 + margin_inner,
        sku_box_x2 - margin_inner,
        sku_box_y1 + 14,
        reference,
        font_ref,
    )

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

