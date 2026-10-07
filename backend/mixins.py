# # backend/mixins.py

# from __future__ import annotations

# from datetime import date, datetime
# from io import BytesIO
# from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# from django.http import HttpResponse
# from django.utils import timezone
# from openpyxl import Workbook
# from openpyxl.utils import get_column_letter

# # ============================================================
# # Helpers date / timezone
# # ============================================================

# def aware_range_month(
#     year: int,
#     month: int,
#     tz,
# ):
#     """
#     Retourne une période mensuelle sous la forme [start, end).

#     Exemple :
#         2026-01
#         start = 2026-01-01 00:00
#         end   = 2026-02-01 00:00

#     La borne de fin est exclusive.
#     """

#     try:
#         year = int(year)
#         month = int(month)
#     except (TypeError, ValueError) as exc:
#         raise ValueError(
#             "L'année et le mois doivent être des entiers."
#         ) from exc

#     if month < 1 or month > 12:
#         raise ValueError(
#             "Le mois doit être compris entre 1 et 12."
#         )

#     start_date = date(
#         year,
#         month,
#         1,
#     )

#     if month == 12:
#         end_date = date(
#             year + 1,
#             1,
#             1,
#         )
#     else:
#         end_date = date(
#             year,
#             month + 1,
#             1,
#         )

#     start_dt = timezone.make_aware(
#         datetime.combine(
#             start_date,
#             datetime.min.time(),
#         ),
#         timezone=tz,
#     )

#     end_dt = timezone.make_aware(
#         datetime.combine(
#             end_date,
#             datetime.min.time(),
#         ),
#         timezone=tz,
#     )

#     return start_dt, end_dt


# def parse_month_or_default(
#     mois_str: str | None,
# ):
#     """
#     Parse le paramètre mois=YYYY-MM.

#     Si le paramètre est absent, utilise le mois courant.

#     Retourne :
#         (
#             annee,
#             mois_num,
#             mois_str_normalise,
#         )
#     """

#     today = timezone.localdate()

#     if not mois_str:
#         return (
#             today.year,
#             today.month,
#             today.strftime("%Y-%m"),
#         )

#     normalized = str(mois_str).strip()

#     try:
#         parsed = datetime.strptime(
#             normalized,
#             "%Y-%m",
#         )
#     except (TypeError, ValueError) as exc:
#         raise ValueError(
#             "Format invalide. Utiliser mois=YYYY-MM."
#         ) from exc

#     normalized = parsed.strftime("%Y-%m")

#     return (
#         parsed.year,
#         parsed.month,
#         normalized,
#     )


# def resolve_tz(
#     tz_name: str | None,
# ):
#     """
#     Résout une timezone IANA.

#     Exemple :
#         Africa/Dakar

#     Si aucune timezone n'est fournie,
#     retourne la timezone active du projet.
#     """

#     if not tz_name:
#         return timezone.get_current_timezone()

#     normalized = str(tz_name).strip()

#     if not normalized:
#         return timezone.get_current_timezone()

#     try:
#         return ZoneInfo(normalized)
#     except ZoneInfoNotFoundError as exc:
#         raise ValueError(
#             "Timezone invalide. Exemple : tz=Africa/Dakar."
#         ) from exc


# # ============================================================
# # Constantes de rapport
# # ============================================================

# GROUP_BY_CHOICES = {
#     "lines",
#     "day",
#     "produit",
#     "vendor",
#     "bijouterie",
# }


# ORDERING_MAP = {
#     # Jour
#     "date": "date",
#     "-date": "-date",
#     "total_ht": "total_ht",
#     "-total_ht": "-total_ht",
#     "total_ttc": "total_ttc",
#     "-total_ttc": "-total_ttc",
#     "quantite": "quantite",
#     "-quantite": "-quantite",

#     # Produit
#     "produit": "produit",
#     "-produit": "-produit",

#     # Vendeur
#     "vendor_email": "vendor_email",
#     "-vendor_email": "-vendor_email",

#     # Bijouterie
#     "bijouterie_nom": "bijouterie_nom",
#     "-bijouterie_nom": "-bijouterie_nom",
# }


# # ============================================================
# # Export Excel
# # ============================================================

# class ExportXlsxMixin:
#     """
#     Mixin permettant de renvoyer un classeur Excel.

#     Exemple :

#         class MaVue(ExportXlsxMixin, APIView):
#             def get(self, request):
#                 wb = Workbook()
#                 return self._xlsx_response(
#                     wb,
#                     "rapport.xlsx",
#                 )
#     """

#     def _xlsx_response(
#         self,
#         wb: Workbook,
#         filename: str,
#     ) -> HttpResponse:
#         """
#         Génère une réponse HTTP contenant un fichier XLSX.
#         """

#         safe_filename = (
#             str(filename or "export.xlsx")
#             .replace('"', "")
#             .replace("\n", "")
#             .replace("\r", "")
#             .strip()
#         )

#         if not safe_filename.lower().endswith(".xlsx"):
#             safe_filename = f"{safe_filename}.xlsx"

#         output = BytesIO()

#         wb.save(output)
#         output.seek(0)

#         response = HttpResponse(
#             output.getvalue(),
#             content_type=(
#                 "application/vnd.openxmlformats-officedocument."
#                 "spreadsheetml.sheet"
#             ),
#         )

#         response["Content-Disposition"] = (
#             f'attachment; filename="{safe_filename}"'
#         )

#         return response

#     def _autosize(
#         self,
#         ws,
#         *,
#         min_width: int = 10,
#         max_width: int = 50,
#     ):
#         """
#         Ajuste automatiquement la largeur des colonnes.
#         """

#         if min_width <= 0:
#             raise ValueError(
#                 "min_width doit être supérieur à zéro."
#             )

#         if max_width < min_width:
#             raise ValueError(
#                 "max_width doit être supérieur ou égal à min_width."
#             )

#         for column_cells in ws.columns:
#             first_cell = column_cells[0]

#             column_letter = get_column_letter(
#                 first_cell.column
#             )

#             max_length = 0

#             for cell in column_cells:
#                 value = cell.value

#                 if value is None:
#                     continue

#                 max_length = max(
#                     max_length,
#                     len(str(value)),
#                 )

#             adjusted_width = max(
#                 min_width,
#                 min(
#                     max_length + 2,
#                     max_width,
#                 ),
#             )

#             ws.column_dimensions[
#                 column_letter
#             ].width = adjusted_width
    
    


# backend/mixins.py

from __future__ import annotations

import calendar
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.utils import get_column_letter

# ============================================================
# Constantes
# ============================================================

GROUP_BY_CHOICES = {
    "day",
    "week",
    "month",
    "year",
}


ORDERING_MAP = {
    "date": "date",
    "-date": "-date",
    "created_at": "created_at",
    "-created_at": "-created_at",
    "updated_at": "updated_at",
    "-updated_at": "-updated_at",
}


# ============================================================
# Gestion des fuseaux horaires
# ============================================================

def resolve_tz(tz_name=None):
    """
    Retourne un fuseau horaire valide.

    Si tz_name est absent :
        utilise le fuseau courant de Django.

    Si tz_name est invalide :
        utilise également le fuseau courant de Django.

    Exemple :

        tz = resolve_tz("Africa/Dakar")
    """

    if not tz_name:
        return timezone.get_current_timezone()

    try:
        return ZoneInfo(
            str(tz_name).strip()
        )
    except (
        ZoneInfoNotFoundError,
        ValueError,
        TypeError,
    ):
        return timezone.get_current_timezone()


# ============================================================
# Gestion des mois
# ============================================================

def parse_month_or_default(
    mois_str=None,
):
    """
    Parse un mois au format :

        YYYY-MM

    Exemple :

        2026-10

    Si la valeur est absente ou invalide,
    retourne le mois courant.

    Retour :

        (year, month)

    Exemple :

        year, month = parse_month_or_default(
            "2026-10"
        )
    """

    now = timezone.localtime()

    if not mois_str:
        return now.year, now.month

    try:
        normalized = str(
            mois_str
        ).strip()

        parsed = datetime.strptime(
            normalized,
            "%Y-%m",
        )

        return (
            parsed.year,
            parsed.month,
        )

    except (
        TypeError,
        ValueError,
    ):
        return (
            now.year,
            now.month,
        )


# ============================================================
# Intervalle d'un mois
# ============================================================

def aware_range_month(
    year: int,
    month: int,
    tz=None,
):
    """
    Retourne l'intervalle timezone-aware correspondant
    à un mois complet.

    Retour :

        (
            start_datetime,
            end_datetime,
        )

    L'intervalle est semi-ouvert :

        start <= date < end

    Exemple pour octobre 2026 :

        start = 2026-10-01 00:00:00
        end   = 2026-11-01 00:00:00

    Cette approche est préférable à :

        2026-10-31 23:59:59.999999

    car elle évite les problèmes de précision.
    """

    if not isinstance(year, int):
        raise TypeError(
            "year doit être un entier."
        )

    if not isinstance(month, int):
        raise TypeError(
            "month doit être un entier."
        )

    if month < 1 or month > 12:
        raise ValueError(
            "month doit être compris entre 1 et 12."
        )

    tz = tz or timezone.get_current_timezone()

    start_naive = datetime(
        year,
        month,
        1,
        0,
        0,
        0,
    )

    # --------------------------------------------------------
    # Premier jour du mois suivant
    # --------------------------------------------------------

    if month == 12:
        next_year = year + 1
        next_month = 1
    else:
        next_year = year
        next_month = month + 1

    end_naive = datetime(
        next_year,
        next_month,
        1,
        0,
        0,
        0,
    )

    start = timezone.make_aware(
        start_naive,
        timezone=tz,
    )

    end = timezone.make_aware(
        end_naive,
        timezone=tz,
    )

    return start, end


# ============================================================
# Nombre de jours dans un mois
# ============================================================

def days_in_month(
    year: int,
    month: int,
) -> int:
    """
    Retourne le nombre de jours dans un mois.

    Exemple :

        days_in_month(2026, 10)
        -> 31
    """

    return calendar.monthrange(
        year,
        month,
    )[1]


# ============================================================
# Export Excel
# ============================================================

class ExportXlsxMixin:
    """
    Mixin utilitaire pour générer des fichiers XLSX.

    Ce mixin ne contient aucune logique :
    - de rôle ;
    - de permission ;
    - de bijouterie ;
    - de filtrage métier.

    Le queryset doit être sécurisé AVANT
    la génération du fichier Excel.
    """

    xlsx_content_type = (
        "application/"
        "vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet"
    )

    # --------------------------------------------------------
    # Création d'une réponse XLSX
    # --------------------------------------------------------

    def _xlsx_response(
        self,
        workbook: Workbook,
        filename: str,
    ) -> HttpResponse:
        """
        Transforme un Workbook openpyxl en HttpResponse.

        Exemple :

            workbook = Workbook()

            return self._xlsx_response(
                workbook,
                "ventes.xlsx",
            )
        """

        if workbook is None:
            raise ValueError(
                "Le workbook est obligatoire."
            )

        filename = str(
            filename or "export.xlsx"
        ).strip()

        if not filename:
            filename = "export.xlsx"

        if not filename.lower().endswith(
            ".xlsx"
        ):
            filename = f"{filename}.xlsx"

        output = BytesIO()

        workbook.save(output)

        output.seek(0)

        response = HttpResponse(
            output.getvalue(),
            content_type=self.xlsx_content_type,
        )

        response[
            "Content-Disposition"
        ] = (
            f'attachment; filename="{filename}"'
        )

        return response

    # --------------------------------------------------------
    # Ajustement automatique des colonnes
    # --------------------------------------------------------

    def _autosize(
        self,
        worksheet,
        *,
        min_width: int = 10,
        max_width: int = 50,
        padding: int = 2,
    ):
        """
        Ajuste automatiquement la largeur
        des colonnes d'une feuille Excel.

        min_width :
            largeur minimale.

        max_width :
            largeur maximale.

        padding :
            espace supplémentaire ajouté
            après la valeur la plus longue.
        """

        if worksheet is None:
            return

        min_width = max(
            int(min_width),
            1,
        )

        max_width = max(
            int(max_width),
            min_width,
        )

        padding = max(
            int(padding),
            0,
        )

        for column_index, column_cells in enumerate(
            worksheet.iter_cols(),
            start=1,
        ):
            max_length = 0

            for cell in column_cells:
                value = cell.value

                if value is None:
                    continue

                try:
                    length = len(
                        str(value)
                    )
                except Exception:
                    continue

                if length > max_length:
                    max_length = length

            width = max_length + padding

            width = max(
                width,
                min_width,
            )

            width = min(
                width,
                max_width,
            )

            column_letter = get_column_letter(
                column_index
            )

            worksheet.column_dimensions[
                column_letter
            ].width = width

        return worksheet
    
    