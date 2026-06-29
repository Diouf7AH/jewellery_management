from io import BytesIO
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

# ============================================================
# Étiquette Rio Gold - Phomemo M221
# Format : 30 x 25 mm
# Résolution : 203 DPI ≈ 240 x 200 px
#
# Disposition :
# - Gauche : QR Code 11 x 11 mm + SKU court
# - Droite : RIO GOLD / PURETÉ / 18K / MARQUE / POIDS / 2.50 g
#
# QR contenu :
# - P:<produit.uuid>
# ============================================================


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    Charge une police compatible Windows + Linux.
    Sur VPS Linux : DejaVuSans-Bold.ttf
    Sur Windows local : Arial Bold
    """
    font_paths = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    for font_path in font_paths:
        if Path(font_path).exists():
            return ImageFont.truetype(font_path, size)

    return ImageFont.load_default()


def _center_text(draw: ImageDraw.ImageDraw, x1: int, x2: int, y: int, text: str, font):
    """
    Centre un texte entre x1 et x2.
    """
    text = str(text or "")
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = x1 + ((x2 - x1 - text_width) // 2)
    draw.text((x, y), text, fill="black", font=font)


def build_etiquette_bague_png(produit) -> BytesIO:
    """
    Génère une étiquette PNG pour Phomemo M221.

    Format réel :
    - 30 mm x 25 mm
    - 203 DPI
    - 240 px x 200 px

    Le QR code contient l'identifiant technique stable :
    - P:<produit.uuid>

    Le SKU court affiché est :
    - CAT-MOD-ETAT
    Exemple :
    - BAG-ALL-N
    """

    # Dimensions 30 x 25 mm à 203 DPI
    width = 240
    height = 200

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    # Polices
    font_title = _load_font(20)
    font_label = _load_font(14)
    font_purete = _load_font(38)
    font_marque = _load_font(20)
    font_poids = _load_font(28)
    font_sku = _load_font(16)

    # ------------------------------------------------------------
    # Données produit
    # ------------------------------------------------------------

    qr_content = f"P:{produit.uuid}" if getattr(produit, "uuid", None) else f"P:{produit.id}"

    purete = str(produit.purete) if getattr(produit, "purete", None) else ""
    poids = f"{produit.poids} g" if getattr(produit, "poids", None) else ""

    categorie_nom = (
        produit.categorie.nom
        if getattr(produit, "categorie", None) and getattr(produit.categorie, "nom", None)
        else ""
    )

    modele_nom = (
        produit.modele.modele
        if getattr(produit, "modele", None) and getattr(produit.modele, "modele", None)
        else ""
    )

    etat = getattr(produit, "etat", "") or ""

    marque = (
        produit.marque.marque
        if getattr(produit, "marque", None) and getattr(produit.marque, "marque", None)
        else ""
    )

    sku_court = (
        f"{categorie_nom[:3].upper()}-"
        f"{modele_nom[:3].upper()}-"
        f"{etat.upper()}"
    ).strip("-")

    marque_courte = marque[:5].upper()

    # ------------------------------------------------------------
    # Zone gauche : QR + SKU
    # ------------------------------------------------------------

    # 2 mm ≈ 16 px à 203 DPI
    # QR 11 x 11 mm ≈ 88 px
    qr_size = 88
    qr_x = 16
    qr_y = 14

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

    # NEAREST garde les modules QR nets pour impression thermique
    qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.NEAREST)
    img.paste(qr_img, (qr_x, qr_y))

    # SKU sous le QR, sans cadre
    _center_text(
        draw=draw,
        x1=8,
        x2=112,
        y=112,
        text=sku_court,
        font=font_sku,
    )

    # ------------------------------------------------------------
    # Zone droite : informations produit
    # ------------------------------------------------------------

    right_x1 = 112
    right_x2 = width - 16  # marge droite ≈ 2 mm

    _center_text(draw, right_x1, right_x2, 10, "RIO GOLD", font_title)

    _center_text(draw, right_x1, right_x2, 42, "PURETÉ", font_label)
    _center_text(draw, right_x1, right_x2, 56, purete, font_purete)

    _center_text(draw, right_x1, right_x2, 105, marque_courte, font_marque)

    _center_text(draw, right_x1, right_x2, 130, "POIDS", font_label)
    _center_text(draw, right_x1, right_x2, 148, poids, font_poids)

    # ------------------------------------------------------------
    # Sortie PNG en mémoire
    # ------------------------------------------------------------

    output = BytesIO()
    img.save(output, format="PNG")
    output.seek(0)

    return output
