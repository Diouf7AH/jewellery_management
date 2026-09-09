# # sale/pdf/escpos_ticket_58mm.py

# from __future__ import annotations

# from decimal import ROUND_HALF_UP, Decimal
# from typing import Optional

# from django.utils import timezone

# # Font A standard sur ticket 58mm
# LINE_WIDTH = 32
# LINE = "-" * LINE_WIDTH


# def _money(x) -> str:
#     try:
#         d = Decimal(str(x or "0")).quantize(
#             Decimal("1"),
#             rounding=ROUND_HALF_UP,
#         )
#     except Exception:
#         return str(x)

#     return f"{d:,}".replace(",", " ") + " FCFA"


# def _txt(s: str) -> bytes:
#     return (
#         str(s or "") + "\n"
#     ).encode(
#         "cp1252",
#         errors="replace",
#     )


# def _fit(
#     text: str,
#     width: int = LINE_WIDTH,
# ) -> str:
#     text = str(text or "")

#     if len(text) <= width:
#         return text

#     if width <= 3:
#         return text[:width]

#     return text[: width - 3] + "..."


# def _left_right(
#     left: str,
#     right: str,
#     width: int = LINE_WIDTH,
# ) -> str:

#     left = str(left or "").strip()
#     right = str(right or "").strip()

#     if not left:
#         return _fit(right, width)

#     if not right:
#         return _fit(left, width)

#     if len(right) >= width:
#         return right[:width]

#     max_left = width - len(right) - 1

#     if len(left) > max_left:
#         if max_left > 3:
#             left = left[: max_left - 3] + "..."
#         else:
#             left = left[:max_left]

#     spaces = width - len(left) - len(right)

#     if spaces < 1:
#         spaces = 1

#     return f"{left}{' ' * spaces}{right}"


# def _normalize_datetime(value):
#     if value is None:
#         return timezone.localtime(timezone.now())

#     try:
#         if timezone.is_naive(value):
#             value = timezone.make_aware(
#                 value,
#                 timezone.get_current_timezone(),
#             )

#         return timezone.localtime(value)

#     except Exception:
#         return timezone.localtime(timezone.now())


# def _split_date_time(date_txt: Optional[str]):
#     value = str(date_txt or "").strip()

#     if not value:
#         dt = _normalize_datetime(None)
#         return (
#             dt.strftime("%d/%m/%Y"),
#             dt.strftime("%H:%M"),
#         )

#     parts = value.split()

#     if len(parts) >= 2:
#         return parts[0], parts[1]

#     return value, ""


# def build_escpos_ticket_proforma_58mm(
#     *,
#     shop_name: str = "BIJOUTERIE RIO-GOLD",
#     shop_phone: Optional[str] = None,
#     numero_facture: str,
#     date_txt: Optional[str] = None,
#     montant_a_payer=Decimal("0"),
#     statut_txt: str = "NON PAYE",
#     note: Optional[str] = "Ticket PROFORMA a regler en caisse.",
# ) -> bytes:

#     # ========================================================
#     # DATE
#     # ========================================================

#     if not date_txt:
#         dt = _normalize_datetime(None)
#         date_txt = dt.strftime("%d/%m/%Y %H:%M")

#     date_only, heure_only = _split_date_time(date_txt)

#     # ========================================================
#     # COMMANDES ESC/POS
#     # ========================================================

#     INIT = b"\x1b@"

#     ALIGN_LEFT = b"\x1ba\x00"
#     ALIGN_CENTER = b"\x1ba\x01"

#     BOLD_ON = b"\x1bE\x01"
#     BOLD_OFF = b"\x1bE\x00"

#     DOUBLE_ON = b"\x1d!\x11"
#     DOUBLE_OFF = b"\x1d!\x00"

#     # Font A / Font B
#     FONT_A = b"\x1bM\x00"
#     FONT_B = b"\x1bM\x01"

#     # coupe partielle
#     CUT_PARTIAL = b"\x1dV\x01"

#     out = bytearray()

#     # ========================================================
#     # INIT
#     # ========================================================

#     out += INIT
#     out += ALIGN_CENTER
#     out += FONT_A

#     # Marge supérieure avant l'en-tête
#     out += b"\n\n"
    
#     # ========================================================
#     # EN-TETE
#     # ========================================================

#     out += BOLD_ON
#     out += _txt(_fit(shop_name.upper()))
#     out += BOLD_OFF

#     if shop_phone:
#         out += _txt(
#             _fit(f"Tel: {shop_phone}")
#         )

#     out += _txt(LINE)

#     # ========================================================
#     # FACTURE PROFORMA + NUMERO SUR UNE SEULE LIGNE
#     # ========================================================

#     # Font B permet d'avoir plus de caractères sur 58mm
#     out += FONT_B
#     out += ALIGN_LEFT
#     out += BOLD_ON

#     title = "FACTURE PROFORMA"
#     numero = f"N° {numero_facture}"

#     # Font B ≈ 42 caractères sur 58 mm
#     line_width_b = 42

#     out += _txt(
#         _left_right(
#             title,
#             numero,
#             line_width_b,
#         )
#     )

#     out += BOLD_OFF

#     out += _txt("-" * line_width_b)

#     # ========================================================
#     # DATE + HEURE SUR UNE SEULE LIGNE
#     # ========================================================

#     out += _txt(
#         _left_right(
#             f"DATE : {date_only}",
#             heure_only,
#             line_width_b,
#         )
#     )

#     # ========================================================
#     # ETAT SUR UNE SEULE LIGNE
#     # ========================================================

#     statut = (
#         str(statut_txt or "NON PAYE")
#         .strip()
#         .upper()
#         .replace("É", "E")
#     )

#     out += _txt(
#         f"ETAT : {statut}"
#     )

#     out += _txt("-" * line_width_b)

#     # ========================================================
#     # MONTANT A PAYER
#     # ========================================================

#     out += ALIGN_CENTER
#     out += FONT_A
#     out += BOLD_ON

#     out += _txt("MONTANT A PAYER")

#     # montant juste en dessous
#     out += DOUBLE_ON

#     out += _txt(
#         _fit(
#             _money(montant_a_payer)
#         )
#     )

#     out += DOUBLE_OFF
#     out += BOLD_OFF

#     out += _txt(LINE)

#     # ========================================================
#     # NOTE
#     # ========================================================

#     if note:
#         out += _txt(
#             _fit(note)
#         )

#     # ========================================================
#     # MESSAGE FINAL
#     # ========================================================

#     out += ALIGN_CENTER
#     out += BOLD_ON

#     out += _txt(
#         "Merci pour votre confiance !"
#     )

#     out += b"\n\n\n\n"
#     out += CUT_PARTIAL

#     return bytes(out)


# sale/pdf/escpos_ticket_58mm.py

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from django.utils import timezone

# ============================================================
# CONFIGURATION
# ============================================================

# Font B est plus petite que Font A.
# Sur une imprimante 58 mm, elle permet environ 42 caractères.
LINE_WIDTH = 32
LINE = "-" * LINE_WIDTH


# ============================================================
# HELPERS
# ============================================================

def _money(x) -> str:
    try:
        d = Decimal(str(x or "0")).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    except Exception:
        return str(x)

    return f"{d:,}".replace(",", " ") + " FCFA"


def _txt(s: str) -> bytes:
    return (
        str(s or "") + "\n"
    ).encode(
        "cp1252",
        errors="replace",
    )


def _fit(
    text: str,
    width: int = LINE_WIDTH,
) -> str:

    text = str(text or "")

    if len(text) <= width:
        return text

    if width <= 3:
        return text[:width]

    return text[: width - 3] + "..."


def _left_right(
    left: str,
    right: str,
    width: int = LINE_WIDTH,
) -> str:

    left = str(left or "").strip()
    right = str(right or "").strip()

    if not left:
        return _fit(right, width)

    if not right:
        return _fit(left, width)

    if len(right) >= width:
        return right[:width]

    max_left = width - len(right) - 1

    if max_left < 0:
        max_left = 0

    if len(left) > max_left:

        if max_left > 3:
            left = (
                left[: max_left - 3]
                + "..."
            )
        else:
            left = left[:max_left]

    spaces = (
        width
        - len(left)
        - len(right)
    )

    if spaces < 1:
        spaces = 1

    return (
        f"{left}"
        f"{' ' * spaces}"
        f"{right}"
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

        return timezone.localtime(value)

    except Exception:

        return timezone.localtime(
            timezone.now()
        )


def _split_date_time(
    date_txt: Optional[str],
):

    value = str(
        date_txt or ""
    ).strip()

    if not value:

        dt = _normalize_datetime(None)

        return (
            dt.strftime("%d/%m/%Y"),
            dt.strftime("%H:%M"),
        )

    parts = value.split()

    if len(parts) >= 2:
        return parts[0], parts[1]

    return value, ""


# ============================================================
# TICKET PROFORMA ESC/POS 58 MM
# ============================================================

def build_escpos_ticket_proforma_58mm(
    *,
    shop_name: str = "BIJOUTERIE RIO-GOLD",
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
    # DATE
    # ========================================================

    if not date_txt:

        dt = _normalize_datetime(None)

        date_txt = dt.strftime(
            "%d/%m/%Y %H:%M"
        )

    date_only, heure_only = (
        _split_date_time(date_txt)
    )

    # ========================================================
    # COMMANDES ESC/POS
    # ========================================================

    INIT = b"\x1b@"

    ALIGN_LEFT = b"\x1ba\x00"
    ALIGN_CENTER = b"\x1ba\x01"

    BOLD_ON = b"\x1bE\x01"
    BOLD_OFF = b"\x1bE\x00"

    # Font A = plus grande
    FONT_A = b"\x1bM\x00"

    # Font B = plus petite
    FONT_B = b"\x1bM\x01"

    # Taille normale
    NORMAL_SIZE = b"\x1d!\x00"

    # Coupe partielle
    CUT_PARTIAL = b"\x1dV\x01"

    out = bytearray()

    # ========================================================
    # INITIALISATION
    # ========================================================

    out += INIT
    out += NORMAL_SIZE

    # On utilise Font B pour le ticket :
    # écriture légèrement plus petite.
    out += FONT_B

    out += ALIGN_CENTER

    # ========================================================
    # MARGE SUPÉRIEURE
    # ========================================================

    # 2 lignes avant l'en-tête
    out += b"\n"

    # ========================================================
    # EN-TÊTE
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

    out += _txt(LINE)

    # ========================================================
    # FACTURE PROFORMA + NUMÉRO
    # ========================================================

    out += ALIGN_LEFT
    out += BOLD_ON

    out += _txt(
        _left_right(
            "FACTURE PROFORMA",
            f"N° {numero_facture}",
        )
    )

    out += BOLD_OFF

    out += _txt(LINE)

    # ========================================================
    # DATE + HEURE
    # ========================================================

    out += _txt(
        _left_right(
            f"DATE : {date_only}",
            heure_only,
        )
    )

    # ========================================================
    # ÉTAT
    # ========================================================

    statut = (
        str(
            statut_txt
            or "NON PAYE"
        )
        .strip()
        .upper()
        .replace("É", "E")
    )

    out += BOLD_ON

    out += _txt(
        f"ETAT : {statut}"
    )

    out += BOLD_OFF

    out += _txt(LINE)

    # ========================================================
    # MONTANT À PAYER
    # ========================================================

    out += ALIGN_CENTER

    # Titre en petite Font B
    out += FONT_B
    out += BOLD_ON

    out += _txt(
        "MONTANT A PAYER"
    )

    # --------------------------------------------------------
    # Montant légèrement plus grand
    # --------------------------------------------------------

    # On passe seulement le montant en Font A.
    # Pas de DOUBLE_ON : il ne sera donc pas énorme.
    out += FONT_A

    out += _txt(
        _fit(
            _money(
                montant_a_payer
            ),
            32,
        )
    )

    # Retour à la petite police
    out += FONT_B

    out += BOLD_OFF

    out += _txt(LINE)

    # ========================================================
    # NOTE
    # ========================================================

    if note:

        out += ALIGN_CENTER
        out += FONT_B

        out += _txt(
            _fit(note)
        )

    # ========================================================
    # MESSAGE FINAL
    # ========================================================

    out += ALIGN_CENTER
    out += FONT_B
    out += BOLD_ON

    out += _txt(
        "Merci pour votre confiance !"
    )

    out += BOLD_OFF

    # ========================================================
    # MARGE INFÉRIEURE
    # ========================================================

    # Exactement 4 lignes après le message
    out += b"\n"

    # ========================================================
    # COUPE
    # ========================================================

    out += CUT_PARTIAL

    return bytes(out)

