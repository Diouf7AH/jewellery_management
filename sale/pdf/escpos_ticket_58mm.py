# sale/pdf/escpos_ticket_58mm.py

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from django.utils import timezone

# ============================================================
# CONFIGURATION POS-58
# ============================================================

# Police normale
NORMAL_WIDTH = 32

# Mode condensé
CONDENSED_WIDTH = 42

LINE_NORMAL = "-" * NORMAL_WIDTH
LINE_CONDENSED = "-" * CONDENSED_WIDTH


# ============================================================
# HELPERS
# ============================================================

def _money(value) -> str:
    """
    Exemple :
    12500.00 -> 12 500 FCFA
    """

    try:
        amount = Decimal(
            str(value or "0")
        ).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )

    except Exception:
        return str(value)

    return (
        f"{amount:,.0f}"
        .replace(",", " ")
        + " FCFA"
    )


def _txt(value: str) -> bytes:
    """
    Une utilisation de _txt() = une ligne imprimée.
    """

    return (
        str(value or "")
        + "\n"
    ).encode(
        "cp1252",
        errors="replace",
    )


def _fit(
    text: str,
    width: int,
) -> str:
    """
    Empêche une chaîne de dépasser la largeur prévue.
    """

    text = str(
        text or ""
    ).strip()

    if len(text) <= width:
        return text

    if width <= 3:
        return text[:width]

    return (
        text[: width - 3]
        + "..."
    )


def _left_right(
    left: str,
    right: str,
    width: int,
) -> str:
    """
    Place deux valeurs sur UNE SEULE ligne.

    Exemple :
    DATE : 23/09/2026                  22:27
    """

    left = str(
        left or ""
    ).strip()

    right = str(
        right or ""
    ).strip()

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

    # Le texte de droite est trop grand
    if len(right) >= width:
        return right[:width]

    max_left = (
        width
        - len(right)
        - 1
    )

    if len(left) > max_left:
        left = left[:max_left]

    spaces = (
        width
        - len(left)
        - len(right)
    )

    spaces = max(
        spaces,
        1,
    )

    return (
        left
        + (" " * spaces)
        + right
    )


def _normalize_datetime(value):
    if value is None:
        return timezone.localtime(
            timezone.now()
        )

    try:
        if timezone.is_naive(value):
            value = timezone.make_aware(
                value,
                timezone.get_current_timezone(),
            )

        return timezone.localtime(
            value
        )

    except Exception:
        return timezone.localtime(
            timezone.now()
        )


def _split_date_time(
    date_txt: Optional[str],
):
    """
    "23/09/2026 22:27"
        ->
    ("23/09/2026", "22:27")
    """

    value = str(
        date_txt or ""
    ).strip()

    if not value:
        dt = _normalize_datetime(
            None
        )

        return (
            dt.strftime(
                "%d/%m/%Y"
            ),
            dt.strftime(
                "%H:%M"
            ),
        )

    parts = value.split()

    if len(parts) >= 2:
        return (
            parts[0],
            parts[1],
        )

    return (
        value,
        "",
    )


def _normalize_status(
    statut_txt: Optional[str],
) -> str:
    """
    Normalise par exemple :
    Non payée -> NON PAYE
    """

    statut = (
        str(
            statut_txt
            or "NON PAYE"
        )
        .strip()
        .upper()
        .replace("É", "E")
        .replace("È", "E")
        .replace("Ê", "E")
        .replace("À", "A")
    )

    if statut in {
        "NON PAYEE",
        "NON_PAYE",
        "NON_PAYEE",
    }:
        return "NON PAYE"

    return statut


# ============================================================
# BUILD TICKET PROFORMA
# ============================================================

def build_escpos_ticket_proforma_58mm(
    *,
    shop_name: str = "RIO-GOLD",
    shop_phone: Optional[str] = None,
    numero_facture: str,
    date_txt: Optional[str] = None,
    montant_a_payer=Decimal("0"),
    statut_txt: str = "NON PAYE",
    note: Optional[str] = (
        "Ticket PROFORMA a regler en caisse."
    ),
) -> bytes:

    # ========================================================
    # DATE / HEURE
    # ========================================================

    if not date_txt:
        dt = _normalize_datetime(
            None
        )

        date_txt = dt.strftime(
            "%d/%m/%Y %H:%M"
        )

    (
        date_only,
        heure_only,
    ) = _split_date_time(
        date_txt
    )

    # ========================================================
    # STATUT
    # ========================================================

    statut = _normalize_status(
        statut_txt
    )

    # ========================================================
    # COMMANDES ESC/POS
    # ========================================================

    # Initialisation imprimante
    INIT = b"\x1b@"

    # Alignement
    ALIGN_LEFT = b"\x1ba\x00"
    ALIGN_CENTER = b"\x1ba\x01"

    # Gras
    BOLD_ON = b"\x1bE\x01"
    BOLD_OFF = b"\x1bE\x00"

    # Font A
    FONT_A = b"\x1bM\x00"

    # Taille normale
    NORMAL_SIZE = b"\x1d!\x00"

    # Mode condensé
    CONDENSED_ON = b"\x1b\x0f"
    CONDENSED_OFF = b"\x12"

    # Coupe partielle
    CUT_PARTIAL = b"\x1dV\x01"

    # ========================================================
    # BUFFER
    # ========================================================

    out = bytearray()

    # ========================================================
    # INITIALISATION
    # ========================================================

    out += INIT
    out += FONT_A
    out += NORMAL_SIZE
    out += ALIGN_CENTER

    # ========================================================
    # MARGE HAUTE
    # ========================================================

    out += b"\n\n"

    # ========================================================
    # EN-TÊTE
    # ========================================================

    out += BOLD_ON

    out += _txt(
        _fit(
            shop_name.upper(),
            NORMAL_WIDTH,
        )
    )

    out += BOLD_OFF

    if shop_phone:
        out += _txt(
            _fit(
                f"Tel: {shop_phone}",
                NORMAL_WIDTH,
            )
        )

    out += _txt(
        LINE_NORMAL
    )

    # ========================================================
    # FACTURE / DATE / ETAT
    # MODE CONDENSÉ
    # ========================================================

    out += ALIGN_LEFT
    out += CONDENSED_ON

    # --------------------------------------------------------
    # FACTURE + NUMERO
    # --------------------------------------------------------

    out += BOLD_ON

    out += _txt(
        _left_right(
            "FACTURE PROFORMA",
            f"N° {numero_facture}",
            CONDENSED_WIDTH,
        )
    )

    out += BOLD_OFF

    # --------------------------------------------------------
    # SÉPARATEUR
    # --------------------------------------------------------

    out += _txt(
        LINE_CONDENSED
    )

    # --------------------------------------------------------
    # DATE + HEURE
    # --------------------------------------------------------

    out += _txt(
        _left_right(
            f"DATE : {date_only}",
            heure_only,
            CONDENSED_WIDTH,
        )
    )

    # --------------------------------------------------------
    # ETAT
    # --------------------------------------------------------

    out += BOLD_ON

    out += _txt(
        f"ETAT : {statut}"
    )

    out += BOLD_OFF

    # --------------------------------------------------------
    # SÉPARATEUR
    # --------------------------------------------------------

    out += _txt(
        LINE_CONDENSED
    )

    # ========================================================
    # FIN MODE CONDENSÉ
    # ========================================================

    out += CONDENSED_OFF

    # ========================================================
    # MONTANT A PAYER
    # ========================================================

    out += ALIGN_CENTER

    out += BOLD_ON

    out += _txt(
        "MONTANT A PAYER"
    )

    montant_txt = _money(
        montant_a_payer
    )

    out += _txt(
        _fit(
            montant_txt,
            NORMAL_WIDTH,
        )
    )

    out += BOLD_OFF

    out += _txt(
        LINE_NORMAL
    )

    # ========================================================
    # NOTE
    # ========================================================

    if note:
        out += ALIGN_CENTER

        # Condensé pour garder la note
        # sur une seule ligne si possible.
        out += CONDENSED_ON

        out += _txt(
            _fit(
                note,
                CONDENSED_WIDTH,
            )
        )

        out += CONDENSED_OFF

    # ========================================================
    # MERCI
    # ========================================================

    out += ALIGN_CENTER

    # On utilise aussi le condensé pour éviter
    # un retour automatique sur certaines POS-58.
    out += CONDENSED_ON
    out += BOLD_ON

    out += _txt(
        _fit(
            "Merci pour votre confiance !",
            CONDENSED_WIDTH,
        )
    )

    out += BOLD_OFF
    out += CONDENSED_OFF

    # ========================================================
    # MARGE BASSE : 4 LIGNES
    # ========================================================

    out += b"\n\n\n\n"

    # ========================================================
    # COUPE
    # ========================================================

    out += CUT_PARTIAL

    return bytes(out)

