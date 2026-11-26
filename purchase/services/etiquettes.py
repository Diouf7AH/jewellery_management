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

# Marges de sécurité.
MARGIN_LEFT_MM = 6
MARGIN_RIGHT_MM = 4
MARGIN_TOP_MM = 4
MARGIN_BOTTOM_MM = 4

# Espacement horizontal.
GAP_MM = 0.5

# Taille maximale du QR code.
QR_MAX_SIZE_MM = 14

# Orientation.
ROTATE_LABEL = False


def mm_to_px(mm):
    return round(mm * DPI / 25.4)


LABEL_WIDTH_PX = mm_to_px(LABEL_WIDTH_MM)
LABEL_HEIGHT_PX = mm_to_px(LABEL_HEIGHT_MM)


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
            "Largeur disponible invalide."
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
    Bague              -> BG
    Collier            -> COL
    Bracelet           -> BRA
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
    Exemple : BG-260042-01
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
# GÉNÉRATION DE L'ÉTIQUETTE PNG
# ============================================================

def build_etiquette_produit_png(
    produit_line,
) -> BytesIO:
    """
    Génère une étiquette Rio Gold.

    Imprimante : Phomemo M221.
    Résolution : 203 DPI.

    Format physique : 40 x 30 mm.
    Surface utile : 30 x 22 mm.

    QR code : PL:<uuid ProduitLine>.

    Informations du produit compactes
    et centrées verticalement.

    Le poids affiché correspond au poids
    historique d'achat.
    """

    produit = produit_line.produit

    # ========================================================
    # 1. DIMENSIONS ET MARGES
    # ========================================================

    width = LABEL_WIDTH_PX
    height = LABEL_HEIGHT_PX

    margin_left = mm_to_px(
        MARGIN_LEFT_MM
    )

    margin_right = mm_to_px(
        MARGIN_RIGHT_MM
    )

    margin_top = mm_to_px(
        MARGIN_TOP_MM
    )

    margin_bottom = mm_to_px(
        MARGIN_BOTTOM_MM
    )

    gap = mm_to_px(GAP_MM)

    content_width = (
        width
        - margin_left
        - margin_right
    )

    content_height = (
        height
        - margin_top
        - margin_bottom
    )

    if (
        content_width <= gap
        or content_height <= 0
    ):

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
    # 2. POLICES COMPACTES
    # ========================================================

    font_title = _load_font(15)
    font_label = _load_font(11)
    font_purete = _load_font(25)
    font_marque = _load_font(14)
    font_poids = _load_font(21)
    font_code = _load_font(12)

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

        purete = str(
            produit.purete
        )

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

    available_width = (
        content_width - gap
    )

    # Zone QR : 52 %.
    # Zone informations : 48 %.

    left_width = round(
        available_width * 0.52
    )

    left_x1 = margin_left

    left_x2 = (
        left_x1 + left_width
    )

    right_x1 = (
        left_x2 + gap
    )

    right_x2 = (
        width - margin_right
    )

    top = margin_top

    code_height = 16
    code_gap = 2

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
        mm_to_px(QR_MAX_SIZE_MM),
        left_width,
        content_height - code_height - code_gap,
    )

    box_size = max_qr_size // modules

    if box_size < 2:

        raise ValueError(
            "Surface insuffisante pour générer "
            "un QR code lisible."
        )

    qr.box_size = box_size

    qr_img = qr.make_image(
        fill_color="black",
        back_color="white",
    ).convert("RGB")

    qr_size = qr_img.width

    # ========================================================
    # 10. POSITIONNEMENT DU QR CODE
    # ========================================================

    block_height = (
        qr_size
        + code_gap
        + code_height
    )

    qr_x = left_x2 - qr_size

    qr_y = (
        top
        + (content_height - block_height) // 2
    )

    if (
        qr_x < margin_left
        or qr_y < margin_top
        or qr_x + qr_size > left_x2
        or qr_y + block_height > height - margin_bottom
    ):

        raise ValueError(
            "Le QR code dépasse "
            "la zone d'impression."
        )

    img.paste(
        qr_img,
        (qr_x, qr_y),
    )

    # ========================================================
    # 11. RÉFÉRENCE SOUS LE QR CODE
    # ========================================================

    _center_text(
        draw=draw,
        x1=qr_x,
        x2=qr_x + qr_size,
        y=qr_y + qr_size + code_gap,
        text=code_etiquette,
        font=font_code,
        max_height=code_height,
    )

    # ========================================================
    # 12. POSITIONNEMENT ADAPTATIF DU TEXTE
    # ========================================================

    def right_text(
        position,
        text,
        font,
        height_ratio,
    ):

        y = top + round(
            content_height * position
        )

        max_height = min(
            round(content_height * height_ratio),
            height - margin_bottom - y,
        )

        if max_height <= 0:

            raise ValueError(
                "Position du texte invalide."
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
        position=0.12,
        text="RIO GOLD",
        font=font_title,
        height_ratio=0.10,
    )

    # ========================================================
    # 14. PURETÉ
    # ========================================================

    right_text(
        position=0.24,
        text="PURETÉ",
        font=font_label,
        height_ratio=0.07,
    )

    right_text(
        position=0.34,
        text=purete,
        font=font_purete,
        height_ratio=0.15,
    )

    # ========================================================
    # 15. MARQUE
    # ========================================================

    right_text(
        position=0.51,
        text=marque_courte,
        font=font_marque,
        height_ratio=0.09,
    )

    # ========================================================
    # 16. POIDS
    # ========================================================

    right_text(
        position=0.62,
        text="POIDS",
        font=font_label,
        height_ratio=0.07,
    )

    right_text(
        position=0.72,
        text=poids,
        font=font_poids,
        height_ratio=0.14,
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

