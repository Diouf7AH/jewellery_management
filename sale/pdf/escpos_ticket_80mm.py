from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from django.utils import timezone

LINE_WIDTH = 42
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


def _safe_len(text: str) -> int:
    return len(str(text or ""))


def _left_right(left: str, right: str, width: int = LINE_WIDTH) -> str:
    left = str(left or "").strip()
    right = str(right or "").strip()

    left_len = _safe_len(left)
    right_len = _safe_len(right)

    if left_len + right_len < width:
        return left + (" " * (width - left_len - right_len)) + right

    max_left = max(1, width - right_len - 1)
    if _safe_len(left) > max_left:
        if max_left > 3:
            left = left[: max_left - 3] + "..."
        else:
            left = left[:max_left]

    left_len = _safe_len(left)
    space = width - left_len - right_len

    if space < 1:
        max_right = max(1, width - left_len - 1)
        if _safe_len(right) > max_right:
            right = right[:max_right]
        right_len = _safe_len(right)
        space = max(1, width - left_len - right_len)

    return left + (" " * space) + right


def _normalize_datetime(value):
    if value is None:
        return timezone.localtime(timezone.now())

    try:
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        return timezone.localtime(value)
    except Exception:
        return timezone.localtime(timezone.now())


def build_escpos_recu_paiement_80mm(
    *,
    shop_name: str = "BIJOUTERIE RIO-GOLD",
    shop_phone: Optional[str] = None,
    numero_facture: str,
    date_paiement=None,
    mode_paiement: str = "CASH",
    montant_paye=Decimal("0"),
    reste_a_payer=Decimal("0"),
) -> bytes:
    date_paiement = _normalize_datetime(date_paiement)

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

    out += ALIGN_CENTER + BOLD_ON
    out += _txt(_fit(shop_name))
    out += BOLD_OFF

    if shop_phone:
        out += _txt(_fit(f"Tel: {shop_phone}"))

    out += _txt(LINE)

    out += ALIGN_LEFT
    out += _txt(_left_right("FACTURE", numero_facture))
    out += _txt(_left_right("DATE", date_paiement.strftime("%d/%m/%Y %H:%M")))
    out += _txt(_left_right("MODE", (mode_paiement or "CASH").upper()))
    out += _txt(LINE)

    out += ALIGN_CENTER + BOLD_ON
    out += _txt("MONTANT PAYE")
    out += DOUBLE_ON
    out += _txt(_fit(_money(montant_paye)))
    out += DOUBLE_OFF + BOLD_OFF

    out += ALIGN_LEFT
    out += _txt(LINE)
    out += _txt(_left_right("RESTE A PAYER", _money(reste_a_payer)))
    out += _txt(LINE)

    out += ALIGN_CENTER
    out += _txt("Merci pour votre confiance !")
    out += FEED_3
    out += CUT

    return bytes(out)


