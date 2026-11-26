# purchase/services/etiquettes.py

import re
from io import BytesIO
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

# ============================================================
# CONFIGURATION ÉTIQUETTE RIO GOLD
# Imprimante : Phomemo M221
# ============================================================

DPI = 203

LABEL_WIDTH_MM = 40
LABEL_HEIGHT_MM = 30

MARGIN_MM = 4

# True pour tourner l'image de 90 degrés.
ROTATE_LABEL = False


def mm_to_px(mm):
    return round(mm * DPI / 25.4)


LABEL_WIDTH_PX = mm_to_px(LABEL_WIDTH_MM)
LABEL_HEIGHT_PX = mm_to_px(LABEL_HEIGHT_MM)

MARGIN_PX = mm_to_px(MARGIN_MM)


# ============================================================
# CHARGEMENT DES POLICES
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

            return ImageFont.truetype(
                font_path,
                size,
            )

    try:
        return ImageFont.load_default(size=size)

    except TypeError:
        return ImageFont.load_default()


# ============================================================
# CENTRAGE ET AJUSTEMENT AUTOMATIQUE DU TEXTE
# ============================================================

def _center_text(
    draw,
    x1,
    x2,
    y,
    text,
    font,
    max_height=None,
):

    text = str(text or "")

    if not text:
        return

    available_width = x2 - x1

    if available_width <= 0:
        raise ValueError(
            "Largeur de texte disponible invalide."
        )

    font_size = getattr(font, "size", 14)

    while True:

        bbox = draw.textbbox(
            (0, 0),
            text,
            font=font,
        )

        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        width_ok = (
            text_width <= available_width
        )

        height_ok = (
            max_height is None
            or text_height <= max_height
        )

        if width_ok and height_ok:
            break

        font_size -= 1

        if font_size < 7:

            raise ValueError(
                f"Le texte '{text}' dépasse "
                "la zone d'impression."
            )

        font = _load_font(font_size)

    x = (
        x1
        + (available_width - text_width) // 2
        - bbox[0]
    )

    draw.text(
        (x, y - bbox[1]),
        text,
        fill="black",
        font=font,
    )


# ============================================================
# CODE CATÉGORIE
# ============================================================

def get_categorie_code(produit):
    """
    Retourne le préfixe court de la catégorie.

    Bague             -> BG
    Collier           -> COL
    Bracelet          -> BRA
    Boucles d'oreilles -> BD
    """

    if not getattr(
        produit,
        "categorie",
        None,
    ):
        return "AUT"

    nom = (
        getattr(
            produit.categorie,
            "nom",
            "",
        ) or ""
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
        getattr(
            lot,
            "numero_lot",
            "",
        ) or ""
    ).strip()

    match = re.match(
        r"^LOT-(\d{4})\d{4}-(\d+)$",
        numero_lot,
        re.IGNORECASE,
    )

    if match:

        annee = match.group(1)[-2:]
        numero = match.group(2)

        return (
            f"{annee}"
            f"{numero.zfill(4)}"
        )

    # Fallback.
    if getattr(lot, "id", None):

        return str(lot.id).zfill(6)

    raise ValueError(
        "Impossible de déterminer "
        "le code court du lot."
    )


# ============================================================
# CODE ÉTIQUETTE
# ============================================================

def build_code_etiquette(produit_line):
    """
    Exemple :

        Catégorie : Bague
        Lot : LOT-20260906-0042
        Ligne : 1

        Résultat : BG-260042-01
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
    """
    Génère une étiquette Rio Gold.

    Format physique : 40 x 30 mm.
    Résolution : 203 DPI.
    Surface utile : 32 x 22 mm.
    Marges : 4 mm.

    QR code : PL:<uuid ProduitLine>.

    Le poids affiché correspond au poids
    historique d'achat.
    """

    produit = produit_line.produit

    # ========================================================
    # 1. DIMENSIONS
    # ========================================================

    width = LABEL_WIDTH_PX
    height = LABEL_HEIGHT_PX

    margin = MARGIN_PX

    content_width = width - (2 * margin)
    content_height = height - (2 * margin)

    if content_width <= 0 or content_height <= 0:

        raise ValueError(
            "Dimensions de l'étiquette invalides."
        )

    img = Image.new(
        "RGB",
        (width, height),
        "white",
    )

    draw = ImageDraw.Draw(img)

    # ========================================================
    # 2. POLICES
    # ========================================================

    font_title = _load_font(18)
    font_label = _load_font(12)
    font_purete = _load_font(30)
    font_marque = _load_font(16)
    font_poids = _load_font(24)
    font_code = _load_font(13)

    # ========================================================
    # 3. UUID PRODUITLINE
    # ========================================================

    if not produit_line.uuid:

        raise ValueError(
            f"La ProduitLine #{produit_line.pk} "
            "ne possède pas d'UUID."
        )

    qr_content = f"PL:{produit_line.uuid}"

    # ========================================================
    # 4. CODE ÉTIQUETTE
    # ========================================================

    code_etiquette = build_code_etiquette(
        produit_line
    )

    # ========================================================
    # 5. PURETÉ
    # ========================================================

    purete = ""

    if getattr(produit, "purete", None):

        purete = str(produit.purete)

    # ========================================================
    # 6. POIDS HISTORIQUE D'ACHAT
    # ========================================================

    poids_unitaire_achat = getattr(
        produit_line,
        "poids_unitaire_achat",
        None,
    )

    if poids_unitaire_achat is None:

        raise ValueError(
            f"La ProduitLine #{produit_line.pk} "
            "ne possède pas de poids_unitaire_achat."
        )

    if poids_unitaire_achat <= 0:

        raise ValueError(
            f"Le poids d'achat de la ProduitLine "
            f"#{produit_line.pk} doit être "
            "strictement supérieur à zéro."
        )

    poids = f"{poids_unitaire_achat:.2f} g"

    # ========================================================
    # 7. MARQUE
    # ========================================================

    marque = ""

    if getattr(produit, "marque", None):

        marque = (
            getattr(
                produit.marque,
                "marque",
                "",
            ) or ""
        )

    marque_courte = marque[:7].upper()

    # ========================================================
    # 8. ZONES D'IMPRESSION
    # ========================================================

    left_width = content_width // 2

    left_x1 = margin
    left_x2 = margin + left_width

    right_x1 = left_x2 + 4
    right_x2 = width - margin

    top = margin

    # ========================================================
    # 9. GÉNÉRATION DU QR CODE
    # ========================================================

    qr = qrcode.QRCode(
        version=None,
        error_correction=(
            qrcode.constants.ERROR_CORRECT_M
        ),
        box_size=1,
        border=4,
    )

    qr.add_data(qr_content)

    qr.make(fit=True)

    modules = (
        qr.modules_count
        + 2 * qr.border
    )

    max_qr_size = min(
        left_width - 4,
        content_height - 24,
    )

    # Taille entière de chaque module du QR.
    box_size = max_qr_size // modules

    if box_size < 2:

        raise ValueError(
            "La zone disponible est trop petite "
            "pour générer un QR code lisible."
        )

    qr.box_size = box_size

    qr_img = qr.make_image(
        fill_color="black",
        back_color="white",
    ).convert("RGB")

    qr_size = qr_img.width

    # ========================================================
    # 10. POSITION DU QR CODE
    # ========================================================

    qr_x = (
        left_x1
        + (left_width - qr_size) // 2
    )

    qr_y = (
        top
        + (content_height - qr_size - 20) // 2
    )

    img.paste(
        qr_img,
        (qr_x, qr_y),
    )

    # ========================================================
    # 11. CODE COURT SOUS LE QR CODE
    # ========================================================

    _center_text(
        draw=draw,
        x1=left_x1,
        x2=left_x2,
        y=qr_y + qr_size + 4,
        text=code_etiquette,
        font=font_code,
        max_height=16,
    )

    # ========================================================
    # 12. POSITIONNEMENT VERTICAL ADAPTATIF
    # ========================================================

    # Les positions évoluent automatiquement
    # lorsque MARGIN_MM est modifié.

    def right_text(
        position,
        text,
        font,
        height_ratio,
    ):

        y = top + round(
            content_height * position
        )

        max_height = max(
            1,
            round(content_height * height_ratio),
        )

        _center_text(
            draw=draw,
            x1=right_x1,
            x2=right_x2,
            y=y,
            text=text,
            font=font,
            max_height=max_height,
        )

    # ========================================================
    # 13. NOM DE LA BIJOUTERIE
    # ========================================================

    right_text(
        position=0.02,
        text="RIO GOLD",
        font=font_title,
        height_ratio=0.12,
    )

    # ========================================================
    # 14. PURETÉ
    # ========================================================

    right_text(
        position=0.18,
        text="PURETÉ",
        font=font_label,
        height_ratio=0.08,
    )

    right_text(
        position=0.28,
        text=purete,
        font=font_purete,
        height_ratio=0.19,
    )

    # ========================================================
    # 15. MARQUE
    # ========================================================

    right_text(
        position=0.52,
        text=marque_courte,
        font=font_marque,
        height_ratio=0.11,
    )

    # ========================================================
    # 16. POIDS
    # ========================================================

    right_text(
        position=0.68,
        text="POIDS",
        font=font_label,
        height_ratio=0.08,
    )

    right_text(
        position=0.79,
        text=poids,
        font=font_poids,
        height_ratio=0.16,
    )

    # ========================================================
    # 17. ORIENTATION
    # ========================================================

    if ROTATE_LABEL:

        img = img.transpose(
            Image.Transpose.ROTATE_90
        )

    # ========================================================
    # 18. SORTIE PNG
    # ========================================================

    output = BytesIO()

    img.save(
        output,
        format="PNG",
        dpi=(DPI, DPI),
    )

    output.seek(0)

    return output
