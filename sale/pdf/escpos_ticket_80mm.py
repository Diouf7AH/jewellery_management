from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Optional

from django.utils import timezone

# ============================================================
# CONFIGURATION ESC/POS 80 MM
# ============================================================

LINE_WIDTH = 42
LINE = "-" * LINE_WIDTH

# Une ligne de 42 caractères suppose que l'imprimante
# utilise une police et une largeur compatibles.


# ============================================================
# COMMANDES ESC/POS
# ============================================================

INIT = b"\x1b@"

ALIGN_LEFT = b"\x1ba\x00"
ALIGN_CENTER = b"\x1ba\x01"

BOLD_ON = b"\x1bE\x01"
BOLD_OFF = b"\x1bE\x00"

DOUBLE_ON = b"\x1d!\x11"
DOUBLE_OFF = b"\x1d!\x00"

NORMAL_SIZE = b"\x1d!\x00"


# ============================================================
# HELPERS
# ============================================================

def _decimal_amount(value) -> Decimal:
    """
    Convertit et valide un montant.
    """

    try:
        amount = Decimal(
            str(
                value
                if value is not None
                else "0"
            )
        )

        if not amount.is_finite():
            raise ValueError(
                "Montant non fini."
            )

        return amount

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ) as exc:
        raise ValueError(
            "Montant de paiement invalide."
        ) from exc


def _money(value) -> str:
    """
    Exemple :
        12500.00 -> 12 500 FCFA
    """

    amount = _decimal_amount(value)

    amount = amount.quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    return (
        f"{amount:,.0f}".replace(",", " ")
        + " FCFA"
    )


def _clean_text(value) -> str:
    """
    Nettoie les retours à la ligne et caractères
    de contrôle dans les données imprimées.
    """

    text = str(
        value
        if value is not None
        else ""
    )

    return " ".join(
        text.split()
    ).strip()


def _txt(value: str) -> bytes:
    """
    Convertit une ligne en octets ESC/POS.

    Encodage : CP1252.
    """

    text = _clean_text(value)

    return (
        text + "\n"
    ).encode(
        "cp1252",
        errors="replace",
    )


def _fit(
    text: str,
    width: int = LINE_WIDTH,
) -> str:
    """
    Ajuste un texte à une largeur donnée.
    """

    if width <= 0:
        return ""

    text = _clean_text(text)

    if len(text) <= width:
        return text

    if width <= 3:
        return text[:width]

    return (
        text[:width - 3]
        + "..."
    )


def _left_right(
    left: str,
    right: str,
    width: int = LINE_WIDTH,
) -> str:
    """
    Place deux textes sur une seule ligne.

    Exemple :
    DATE : 13/10/2026                    20:30
    """

    left = _clean_text(left)
    right = _clean_text(right)

    if width <= 0:
        return ""

    if not left:
        return _fit(
            right,
            width,
        )

    if not right:
        return _fit(
            left,
            width,
        )

    if len(right) >= width:
        return _fit(
            right,
            width,
        )

    max_left = (
        width
        - len(right)
        - 1
    )

    left = _fit(
        left,
        max_left,
    )

    spaces = max(
        1,
        width
        - len(left)
        - len(right),
    )

    return (
        left
        + (" " * spaces)
        + right
    )


def _wrap_text(
    value: str,
    width: int = LINE_WIDTH,
) -> list[str]:
    """
    Découpe un texte long sans supprimer
    les informations importantes.

    Utilisé notamment pour les numéros de facture.
    """

    text = _clean_text(value)

    if width <= 0:
        return []

    if not text:
        return [""]

    lines = []

    while len(text) > width:
        lines.append(
            text[:width]
        )

        text = text[width:]

    if text:
        lines.append(text)

    return lines


def _normalize_datetime(value):
    """
    Convertit un datetime vers l'heure locale Django.

    Si aucune date n'est fournie :
    utilise timezone.now().
    """

    if value is None:
        value = timezone.now()

    if not isinstance(
        value,
        datetime,
    ):
        raise ValueError(
            "date_paiement doit être un datetime."
        )

    if timezone.is_aware(value):
        return timezone.localtime(
            value
        )

    if timezone.is_aware(timezone.now()):
        value = timezone.make_aware(
            value,
            timezone.get_current_timezone(),
        )

        return timezone.localtime(
            value
        )

    return value


# ============================================================
# GÉNÉRATION DU REÇU DE PAIEMENT ESC/POS 80 MM
# ============================================================

def build_escpos_recu_paiement_80mm(
    *,
    shop_name: str = "BIJOUTERIE RIO-GOLD",
    shop_phone: Optional[str] = None,
    numero_facture: str,
    date_paiement=None,
    mode_paiement: str = "CASH",
    montant_paye=Decimal("0"),
    reste_a_payer=None,
) -> bytes:
    """
    Génère un reçu de paiement ESC/POS 80 mm.

    Règles :
    - Reçu d'un paiement enregistré.
    - Paiement partiel ou complet.
    - Montant du paiement concerné uniquement.
    - Reste à payer facultatif.
    - Aucun mouvement de stock.
    - Aucune modification financière.

    Retour :
        bytes contenant les commandes ESC/POS.

    Important :
    La vue Django doit fournir les données
    du paiement réellement enregistré.
    """

    # ========================================================
    # 1. VALIDATION
    # ========================================================

    shop_name = _clean_text(
        shop_name or "BIJOUTERIE RIO-GOLD"
    )

    shop_phone = _clean_text(
        shop_phone
    )

    numero_facture = _clean_text(
        numero_facture
    )

    mode_paiement = _clean_text(
        mode_paiement or "CASH"
    ).upper()

    if not numero_facture:
        raise ValueError(
            "Le numéro de facture est obligatoire."
        )

    montant = _decimal_amount(
        montant_paye
    )

    if montant <= Decimal("0"):
        raise ValueError(
            "Le montant payé doit être supérieur à zéro."
        )

    if reste_a_payer is not None:
        reste = _decimal_amount(
            reste_a_payer
        )

        if reste < Decimal("0"):
            raise ValueError(
                "Le reste à payer ne peut pas être négatif."
            )

    # ========================================================
    # 2. DATE / HEURE
    # ========================================================

    date_paiement = _normalize_datetime(
        date_paiement
    )

    date_txt = date_paiement.strftime(
        "%d/%m/%Y"
    )

    heure_txt = date_paiement.strftime(
        "%H:%M"
    )

    # ========================================================
    # 3. BUFFER
    # ========================================================

    out = bytearray()

    # ========================================================
    # 4. INITIALISATION
    # ========================================================

    out += INIT
    out += NORMAL_SIZE
    out += ALIGN_CENTER

    # Marge haute
    out += b"\n\n"

    # ========================================================
    # 5. EN-TÊTE
    # ========================================================

    out += BOLD_ON

    out += _txt(
        _fit(
            shop_name.upper()
        )
    )

    out += BOLD_OFF

    if shop_phone:
        out += _txt(
            _fit(
                f"Tel: {shop_phone}"
            )
        )

    out += _txt(
        LINE
    )

    # ========================================================
    # 6. TITRE
    # ========================================================

    out += BOLD_ON

    out += _txt(
        "RECU DE PAIEMENT"
    )

    out += BOLD_OFF

    out += _txt(
        LINE
    )

    # ========================================================
    # 7. FACTURE
    # ========================================================

    out += ALIGN_LEFT

    numero_label = (
        f"FACTURE : {numero_facture}"
    )

    for line in _wrap_text(
        numero_label
    ):
        out += _txt(
            line
        )

    # ========================================================
    # 8. DATE
    # ========================================================

    out += _txt(
        _left_right(
            f"DATE : {date_txt}",
            heure_txt,
        )
    )

    # ========================================================
    # 9. MODE DE PAIEMENT
    # ========================================================

    mode_label = (
        f"MODE : {mode_paiement}"
    )

    for line in _wrap_text(
        mode_label
    ):
        out += _txt(
            line
        )

    out += _txt(
        LINE
    )

    # ========================================================
    # 10. MONTANT PAYÉ
    # ========================================================

    out += ALIGN_CENTER
    out += BOLD_ON

    out += _txt(
        "MONTANT PAYE"
    )

    montant_txt = _money(
        montant
    )

    # La taille double réduit la largeur disponible.
    # On évite de dépasser 21 caractères.
    if len(montant_txt) <= 21:
        out += DOUBLE_ON

        out += _txt(
            montant_txt
        )

        out += DOUBLE_OFF

    else:
        out += _txt(
            _fit(
                montant_txt
            )
        )

    out += BOLD_OFF

    out += _txt(
        LINE
    )

    # ========================================================
    # 11. RESTE À PAYER
    # ========================================================

    if reste_a_payer is not None:

        out += ALIGN_LEFT

        out += _txt(
            _left_right(
                "RESTE A PAYER",
                _money(reste),
            )
        )

        out += _txt(
            LINE
        )

    # ========================================================
    # 12. MESSAGE FINAL
    # ========================================================

    out += ALIGN_CENTER
    out += BOLD_ON

    out += _txt(
        "Merci pour votre confiance !"
    )

    out += BOLD_OFF

    # ========================================================
    # 13. RESTAURATION
    # ========================================================

    out += NORMAL_SIZE
    out += ALIGN_LEFT

    # ========================================================
    # 14. MARGE BASSE
    # ========================================================

    out += b"\n\n\n\n"

    # ========================================================
    # 15. FIN
    # ========================================================

    # Pas de commande GS V.
    # Certaines imprimantes POS ne reconnaissent pas
    # cette commande et impriment le caractère "V".

    return bytes(out)

