from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from django.utils import timezone

LINE_WIDTH = 32
LINE = "-" * LINE_WIDTH


def _money(x) -> str:
    try:
        d = Decimal(str(x or "0")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except Exception:
        return str(x)
    return f"{d:,}".replace(",", " ") + " FCFA"


def _txt(s: str) -> bytes:
    return (str(s or "") + "\n").encode("cp1252", errors="replace")


def _fit(text: str, width: int = LINE_WIDTH) -> str:
    text = str(text or "")
    if len(text) <= width:
        return text
    return text[: width - 3] + "..."


def _left_right(left: str, right: str, width: int = LINE_WIDTH) -> str:
    left = str(left or "").strip()
    right = str(right or "").strip()

    if len(right) >= width:
        return right[:width]

    max_left = width - len(right) - 1
    if max_left < 0:
        max_left = 0

    if len(left) > max_left:
        if max_left > 3:
            left = left[: max_left - 3] + "..."
        else:
            left = left[:max_left]

    space = width - len(left) - len(right)
    if space < 1:
        space = 1

    return f"{left}{' ' * space}{right}"


def _normalize_datetime(value):
    if value is None:
        return timezone.localtime(timezone.now())

    try:
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        return timezone.localtime(value)
    except Exception:
        return timezone.localtime(timezone.now())


def build_escpos_ticket_proforma_58mm(
    *,
    shop_name: str = "BIJOUTERIE RIO-GOLD",
    shop_phone: Optional[str] = None,
    numero_facture: str,
    date_txt: Optional[str] = None,
    montant_a_payer=Decimal("0"),
    statut_txt: str = "NON PAYEE",
    note: Optional[str] = "Ticket PROFORMA - a regler en caisse",
) -> bytes:
    if not date_txt:
        dt = _normalize_datetime(None)
        date_txt = dt.strftime("%d/%m/%Y %H:%M")

    INIT = b"\x1b@"
    ALIGN_LEFT = b"\x1ba\x00"
    ALIGN_CENTER = b"\x1ba\x01"
    BOLD_ON = b"\x1bE\x01"
    BOLD_OFF = b"\x1bE\x00"
    DOUBLE_ON = b"\x1d!\x11"
    DOUBLE_OFF = b"\x1d!\x00"
    FEED_3 = b"\n\n\n"
    CUT = b"\x1dV\x00"

    out = bytearray()
    out += INIT

    out += ALIGN_CENTER
    out += BOLD_ON
    out += _txt(_fit(shop_name))
    out += BOLD_OFF

    if shop_phone:
        out += _txt(_fit(f"Tel: {shop_phone}"))

    out += _txt(LINE)
    out += _txt("FACTURE PROFORMA")
    out += _txt(LINE)

    out += ALIGN_LEFT
    out += _txt(_left_right("N°", numero_facture))
    out += _txt(_left_right("DATE", date_txt))
    out += _txt(_left_right("ETAT", statut_txt))
    out += _txt(LINE)

    out += ALIGN_CENTER
    out += BOLD_ON
    out += _txt("MONTANT A PAYER")
    out += DOUBLE_ON
    out += _txt(_fit(_money(montant_a_payer)))
    out += DOUBLE_OFF
    out += BOLD_OFF

    out += ALIGN_LEFT
    out += _txt(LINE)

    if note:
        out += _txt(_fit(note))
        out += _txt(LINE)

    out += ALIGN_CENTER
    out += _txt("Merci pour votre confiance")
    out += FEED_3
    out += CUT

    return bytes(out)


