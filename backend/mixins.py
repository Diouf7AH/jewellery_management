# backend/mixins.py
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.utils import get_column_letter

# ============================================================
# 📅 Helpers Date / Timezone
# ============================================================

def aware_range_month(year: int, month: int, tz):
    """
    Retourne [start, end) pour un mois donné.
    Exemple: 2026-01 -> [2026-01-01 00:00, 2026-02-01 00:00)
    """
    first = date(year, month, 1)

    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)

    start_dt = timezone.make_aware(datetime.combine(first, datetime.min.time()), tz)
    end_dt = timezone.make_aware(datetime.combine(last + timedelta(days=1), datetime.min.time()), tz)

    return start_dt, end_dt


def parse_month_or_default(mois_str: str | None):
    """
    Parse `mois=YYYY-MM`.
    Si absent -> mois courant.
    Retourne: (annee, mois_num, mois_str_normalise)
    """
    today = timezone.localdate()

    if not mois_str:
        mois_str = today.strftime("%Y-%m")

    try:
        annee, mois_num = map(int, mois_str.split("-"))
        if mois_num < 1 or mois_num > 12:
            raise ValueError
    except Exception:
        raise ValueError("Format invalide. Utiliser mois=YYYY-MM.")

    return annee, mois_num, mois_str


def resolve_tz(tz_name: str | None):
    """
    Résout une timezone IANA (ex: Africa/Dakar).
    Si absent -> timezone projet.
    """
    if not tz_name:
        return timezone.get_current_timezone()

    try:
        return ZoneInfo(tz_name)
    except Exception:
        raise ValueError("Timezone invalide. Exemple: tz=Africa/Dakar")


# ============================================================
# 📊 Constantes rapport
# ============================================================

GROUP_BY_CHOICES = {"lines", "day", "product", "vendor", "bijouterie"}

ORDERING_MAP = {
    # day
    "date": "date",
    "-date": "-date",
    "total_ht": "total_ht",
    "-total_ht": "-total_ht",
    "total_ttc": "total_ttc",
    "-total_ttc": "-total_ttc",
    "quantite": "quantite",
    "-quantite": "-quantite",

    # product
    "produit": "produit",
    "-produit": "-produit",

    # vendor
    "vendor_email": "vendor_email",
    "-vendor_email": "-vendor_email",

    # bijouterie
    "bijouterie_nom": "bijouterie_nom",
    "-bijouterie_nom": "-bijouterie_nom",
}


# ============================================================
# 📁 Export Excel Mixin
# ============================================================

class ExportXlsxMixin:
    """
    Mixin utilitaire pour renvoyer un fichier Excel (.xlsx)

    Utilisation:
        class MaVue(ExportXlsxMixin, APIView):
            ...
            return self._xlsx_response(wb, "mon_fichier.xlsx")
    """

    def _xlsx_response(self, wb: Workbook, filename: str) -> HttpResponse:
        from io import BytesIO

        bio = BytesIO()
        wb.save(bio)
        bio.seek(0)

        response = HttpResponse(
            bio.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def _autosize(self, ws):
        """
        Ajuste automatiquement la largeur des colonnes.
        """
        for column in ws.columns:
            max_length = 0
            col_letter = get_column_letter(column[0].column)

            for cell in column:
                try:
                    if cell.value is not None:
                        max_length = max(max_length, len(str(cell.value)))
                except Exception:
                    pass

            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[col_letter].width = adjusted_width
            

