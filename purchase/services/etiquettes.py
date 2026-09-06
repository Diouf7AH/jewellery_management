import re
from io import BytesIO
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

# ============================================================
# Étiquette Rio Gold - Phomemo M221
# Format : 30 x 25 mm
# Résolution : 203 DPI ≈ 240 x 200 px
# ============================================================


def _load_font(size: int):
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


def _center_text(draw, x1, x2, y, text, font):
    text = str(text or "")

    bbox = draw.textbbox(
        (0, 0),
        text,
        font=font,
    )

    text_width = bbox[2] - bbox[0]

    x = x1 + ((x2 - x1 - text_width) // 2)

    draw.text(
        (x, y),
        text,
        fill="black",
        font=font,
    )


# ============================================================
# CODE CATÉGORIE
# ============================================================

def get_categorie_code(produit):
    """
    Retourne le préfixe court utilisé sur l'étiquette.

    Exemples :
        Bague              -> BG
        Collier            -> COL
        Bracelet           -> BRA
        Boucles d'oreilles -> BD
    """

    if not getattr(produit, "categorie", None):
        return "AUT"

    nom = (
        getattr(produit.categorie, "nom", "")
        or ""
    ).strip().lower()

    mapping = {
        "bague": "BG",
        "bagues": "BG",

        "collier": "COL",
        "colliers": "COL",

        "bracelet": "BRA",
        "bracelets": "BRA",

        "boucle d'oreille": "BD",
        "boucles d'oreille": "BD",
        "boucles d'oreilles": "BD",
    }

    return mapping.get(
        nom,
        nom[:3].upper() if nom else "AUT",
    )


# ============================================================
# EXTRACTION DU CODE COURT DU LOT
# ============================================================

def get_lot_code_court(lot):
    """
    Exemple :

        LOT-20260906-0042
            ↓
        260042

    26   = année
    0042 = compteur du lot
    """

    numero_lot = str(
        getattr(lot, "numero_lot", "") or ""
    ).strip()

    # Format attendu :
    # LOT-20260906-0042
    match = re.match(
        r"^LOT-(\d{4})\d{4}-(\d+)$",
        numero_lot,
        re.IGNORECASE,
    )

    if match:
        annee = match.group(1)[-2:]
        numero = match.group(2)

        return f"{annee}{numero.zfill(4)}"

    # Fallback sûr
    if getattr(lot, "id", None):
        return str(lot.id).zfill(6)

    raise ValueError(
        "Impossible de déterminer le code court du lot."
    )


# ============================================================
# CODE ÉTIQUETTE
# ============================================================

def build_code_etiquette(produit_line):
    """
    Exemple :

        catégorie        = Bague
        lot              = LOT-20260906-0042
        numero_ligne_lot = 1

        résultat :
        BG-260042-01
    """

    produit = produit_line.produit
    lot = produit_line.lot

    categorie_code = get_categorie_code(
        produit
    )

    lot_code = get_lot_code_court(
        lot
    )

    numero_ligne = (
        produit_line.numero_ligne_lot
    )

    if numero_ligne is None:
        raise ValueError(
            f"La ProduitLine #{produit_line.pk} "
            "ne possède pas de numero_ligne_lot."
        )

    return (
        f"{categorie_code}-"
        f"{lot_code}-"
        f"{numero_ligne:02d}"
    )


# ============================================================
# GÉNÉRATION PNG
# ============================================================

def build_etiquette_produit_png(
    produit_line,
) -> BytesIO:

    produit = produit_line.produit

    # --------------------------------------------------------
    # Dimensions
    # --------------------------------------------------------

    width = 240
    height = 200

    img = Image.new(
        "RGB",
        (width, height),
        "white",
    )

    draw = ImageDraw.Draw(img)

    # --------------------------------------------------------
    # Polices
    # --------------------------------------------------------

    font_title = _load_font(20)
    font_label = _load_font(14)
    font_purete = _load_font(36)
    font_marque = _load_font(18)
    font_poids = _load_font(26)
    font_code = _load_font(15)

    # --------------------------------------------------------
    # UUID
    # --------------------------------------------------------

    produit_uuid = getattr(
        produit,
        "uuid",
        None,
    )

    if not produit_uuid:
        raise ValueError(
            f"Le produit "
            f"#{getattr(produit, 'id', '?')} "
            "ne possède pas d'UUID."
        )

    qr_content = (
        f"P:{produit_uuid}"
    )

    # --------------------------------------------------------
    # Code étiquette
    # --------------------------------------------------------

    code_etiquette = (
        build_code_etiquette(
            produit_line
        )
    )

    # --------------------------------------------------------
    # Pureté
    # --------------------------------------------------------

    purete = ""

    if getattr(produit, "purete", None):
        purete = str(produit.purete)

    # --------------------------------------------------------
    # Poids
    # --------------------------------------------------------

    poids = ""

    if getattr(produit, "poids", None) is not None:
        poids = f"{produit.poids} g"

    # --------------------------------------------------------
    # Marque
    # --------------------------------------------------------

    marque = ""

    if getattr(produit, "marque", None):
        marque = (
            getattr(
                produit.marque,
                "marque",
                "",
            )
            or ""
        )

    marque_courte = (
        marque[:7].upper()
    )

    # --------------------------------------------------------
    # QR
    # --------------------------------------------------------

    qr_size = 88
    qr_x = 16
    qr_y = 14

    qr = qrcode.QRCode(
        version=None,
        error_correction=(
            qrcode.constants.ERROR_CORRECT_M
        ),
        box_size=6,
        border=2,
    )

    qr.add_data(
        qr_content
    )

    qr.make(
        fit=True
    )

    qr_img = (
        qr.make_image(
            fill_color="black",
            back_color="white",
        )
        .convert("RGB")
    )

    qr_img = qr_img.resize(
        (qr_size, qr_size),
        Image.Resampling.NEAREST,
    )

    img.paste(
        qr_img,
        (qr_x, qr_y),
    )

    # --------------------------------------------------------
    # Code court sous QR
    # --------------------------------------------------------

    _center_text(
        draw=draw,
        x1=4,
        x2=112,
        y=111,
        text=code_etiquette,
        font=font_code,
    )

    # --------------------------------------------------------
    # Zone droite
    # --------------------------------------------------------

    right_x1 = 112
    right_x2 = width - 10

    _center_text(
        draw,
        right_x1,
        right_x2,
        8,
        "RIO GOLD",
        font_title,
    )

    _center_text(
        draw,
        right_x1,
        right_x2,
        40,
        "PURETÉ",
        font_label,
    )

    _center_text(
        draw,
        right_x1,
        right_x2,
        54,
        purete,
        font_purete,
    )

    _center_text(
        draw,
        right_x1,
        right_x2,
        103,
        marque_courte,
        font_marque,
    )

    _center_text(
        draw,
        right_x1,
        right_x2,
        130,
        "POIDS",
        font_label,
    )

    _center_text(
        draw,
        right_x1,
        right_x2,
        148,
        poids,
        font_poids,
    )

    # --------------------------------------------------------
    # Sortie PNG
    # --------------------------------------------------------

    output = BytesIO()

    img.save(
        output,
        format="PNG",
    )

    output.seek(0)

    return output


    