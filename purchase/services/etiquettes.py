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

# Espacement vertical des informations.
TEXT_GAP_MM = 0.5

# Taille maximale du QR code.
QR_MAX_SIZE_MM = 14

# Orientation.
ROTATE_LABEL = False


def mm_to_px(mm):
    return round(mm * DPI / 25.4)


LABEL_WIDTH_PX = mm_to_px(LABEL_WIDTH_MM)
LABEL_HEIGHT_PX = mm_to_px(LABEL_HEIGHT_MM)


# ============================================================
# CHARGEMENT DES POLICES EN GRAS
# ============================================================

def _load_font(size: int):

    font_paths = [
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    for font_path in font_paths:

        if Path(font_path).exists():

            return ImageFont.truetype(
                font_path,
                size,
            )

    try:

        return ImageFont.load_default(
            size=size,
        )

    except TypeError:

        return ImageFont.load_default()


# ============================================================
# AJUSTEMENT AUTOMATIQUE DE LA POLICE
# ============================================================

def _fit_font(
    draw,
    text,
    font,
    max_width,
    max_height=None,
):

    text = str(text or "")

    if max_width <= 0:

        raise ValueError(
            "Largeur disponible invalide."
        )

    font_size = getattr(
        font,
        "size",
        14,
    )

    while True:

        bbox = draw.textbbox(
            (0, 0),
            text,
            font=font,
        )

        text_width = bbox[2] - bbox[0]

        text_height = bbox[3] - bbox[1]

        width_ok = (
            text_width <= max_width
        )

        height_ok = (
            max_height is None
            or text_height <= max_height
        )

        if width_ok and height_ok:

            return font, bbox

        font_size -= 1

        if font_size < 7:

            raise ValueError(
                f"Le texte '{text}' dépasse "
                "la zone d'impression."
            )

        font = _load_font(
            font_size
        )


# ============================================================
# CENTRAGE HORIZONTAL DU TEXTE
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

    font, bbox = _fit_font(
        draw=draw,
        text=text,
        font=font,
        max_width=available_width,
        max_height=max_height,
    )

    text_width = bbox[2] - bbox[0]

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
# CENTRAGE HORIZONTAL ET VERTICAL D'UN BLOC DE TEXTE
# ============================================================

def _center_text_block(
    draw,
    x1,
    x2,
    y1,
    y2,
    informations,
    gap,
):

    available_width = x2 - x1

    available_height = y2 - y1

    if (
        available_width <= 0
        or available_height <= 0
    ):

        raise ValueError(
            "Dimensions du bloc de texte invalides."
        )

    lignes = []

    # ========================================================
    # 1. AJUSTEMENT À LA LARGEUR DISPONIBLE
    # ========================================================

    for texte, font in informations:

        texte = str(
            texte or ""
        ).strip()

        if not texte:

            continue

        font, bbox = _fit_font(
            draw=draw,
            text=texte,
            font=font,
            max_width=available_width,
        )

        lignes.append({
            "texte": texte,
            "font": font,
            "height": bbox[3] - bbox[1],
        })

    if not lignes:

        return

    # ========================================================
    # 2. CALCUL DE LA HAUTEUR TOTALE
    # ========================================================

    def calculer_hauteur():

        return (
            sum(
                ligne["height"]
                for ligne in lignes
            )
            + gap * max(
                0,
                len(lignes) - 1,
            )
        )

    total_height = calculer_hauteur()

    # ========================================================
    # 3. AJUSTEMENT AUTOMATIQUE EN HAUTEUR
    # ========================================================

    while total_height > available_height:

        reduction_effectuee = False

        for ligne in lignes:

            font_size = getattr(
                ligne["font"],
                "size",
                14,
            )

            if font_size <= 7:

                continue

            font_size -= 1

            font = _load_font(
                font_size
            )

            font, bbox = _fit_font(
                draw=draw,
                text=ligne["texte"],
                font=font,
                max_width=available_width,
            )

            ligne["font"] = font

            ligne["height"] = (
                bbox[3] - bbox[1]
            )

            reduction_effectuee = True

        if not reduction_effectuee:

            raise ValueError(
                "Les informations du produit "
                "dépassent la hauteur disponible."
            )

        total_height = calculer_hauteur()

    # ========================================================
    # 4. CENTRAGE VERTICAL
    # ========================================================

    current_y = (
        y1
        + (
            available_height
            - total_height
        ) // 2
    )

    # ========================================================
    # 5. AFFICHAGE DES INFORMATIONS
    # ========================================================

    for ligne in lignes:

        _center_text(
            draw=draw,
            x1=x1,
            x2=x2,
            y=current_y,
            text=ligne["texte"],
            font=ligne["font"],
            max_height=ligne["height"],
        )

        current_y += (
            ligne["height"]
            + gap
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

    QR code : PL:<uuid ProduitLine>.

    Colonne gauche :
        - QR code centré.
        - Référence centrée sous le QR code.

    Colonne droite :
        - RIO GOLD.
        - PURETÉ.
        - Valeur de la pureté.
        - Marque.
        - POIDS.
        - Valeur du poids.

    Toutes les informations sont centrées
    horizontalement et verticalement.

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

    gap = mm_to_px(
        GAP_MM
    )

    text_gap = mm_to_px(
        TEXT_GAP_MM
    )

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
    # 2. POLICES AGRANDIES ET EN GRAS
    # ========================================================

    font_title = _load_font(22)

    font_label = _load_font(18)

    font_purete = _load_font(34)

    font_marque = _load_font(24)

    font_poids = _load_font(30)

    font_code = _load_font(15)

    # ========================================================
    # 3. UUID PRODUITLINE
    # ========================================================

    if not produit_line.uuid:

        raise ValueError(
            f"La ProduitLine #{produit_line.pk} "
            "ne possède pas d'UUID."
        )

    qr_content = (
        f"PL:{produit_line.uuid}"
    )

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

    if getattr(
        produit,
        "purete",
        None,
    ):

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

    poids = (
        f"{poids_unitaire_achat:.2f} g"
    )

    # ========================================================
    # 7. MARQUE
    # ========================================================

    marque = ""

    if getattr(
        produit,
        "marque",
        None,
    ):

        marque = (
            getattr(
                produit.marque,
                "marque",
                "",
            ) or ""
        )

    marque_courte = (
        marque[:7].upper()
    )

    # ========================================================
    # 8. ZONES D'IMPRESSION
    # ========================================================

    available_width = (
        content_width - gap
    )

    # Colonne gauche : QR code — 52 %.
    # Colonne droite : informations — 48 %.

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

    bottom = (
        height - margin_bottom
    )

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

    qr.add_data(
        qr_content
    )

    qr.make(
        fit=True
    )

    modules = (
        qr.modules_count
        + 2 * qr.border
    )

    max_qr_size = min(
        mm_to_px(QR_MAX_SIZE_MM),
        left_width,
        content_height
        - code_height
        - code_gap,
    )

    box_size = (
        max_qr_size // modules
    )

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
    # 10. CENTRAGE DU QR CODE ET DE SA RÉFÉRENCE
    # ========================================================

    font_code, code_bbox = _fit_font(
        draw=draw,
        text=code_etiquette,
        font=font_code,
        max_width=left_width,
        max_height=code_height,
    )

    actual_code_height = (
        code_bbox[3] - code_bbox[1]
    )

    block_height = (
        qr_size
        + code_gap
        + actual_code_height
    )

    # Centrage horizontal.

    qr_x = (
        left_x1
        + (left_width - qr_size) // 2
    )

    # Centrage vertical du QR code
    # et de la référence.

    qr_y = (
        top
        + (
            content_height
            - block_height
        ) // 2
    )

    # Vérification des limites.

    if (
        qr_x < left_x1
        or qr_y < top
        or qr_x + qr_size > left_x2
        or qr_y + block_height > bottom
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
    # 11. RÉFÉRENCE CENTRÉE SOUS LE QR CODE
    # ========================================================

    _center_text(
        draw=draw,
        x1=left_x1,
        x2=left_x2,
        y=(
            qr_y
            + qr_size
            + code_gap
        ),
        text=code_etiquette,
        font=font_code,
        max_height=code_height,
    )

    # ========================================================
    # 12. INFORMATIONS DU PRODUIT
    # ========================================================

    informations = [

        (
            "RIO GOLD",
            font_title,
        ),

        (
            "PURETÉ",
            font_label,
        ),

        (
            purete,
            font_purete,
        ),

        (
            marque_courte,
            font_marque,
        ),

        (
            "POIDS",
            font_label,
        ),

        (
            poids,
            font_poids,
        ),
    ]

    # ========================================================
    # 13. CENTRAGE DES INFORMATIONS DU PRODUIT
    # ========================================================

    _center_text_block(
        draw=draw,
        x1=right_x1,
        x2=right_x2,
        y1=top,
        y2=bottom,
        informations=informations,
        gap=text_gap,
    )

    # ========================================================
    # 14. ORIENTATION
    # ========================================================

    if ROTATE_LABEL:

        img = img.transpose(
            Image.Transpose.ROTATE_90
        )

    # ========================================================
    # 15. SORTIE PNG
    # ========================================================

    output = BytesIO()

    img.save(
        output,
        format="PNG",
        dpi=(DPI, DPI),
    )

    output.seek(0)

    return output

