from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Optional

from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.utils import get_column_letter


class ExportXlsxMixin:
    """
    Petit mixin utilitaire pour générer une réponse HTTP avec un fichier Excel.

    Utilisation :
      - Dans ta vue, hérite de ce mixin : class MaView(ExportXlsxMixin, APIView)
      - Crée un Workbook openpyxl
      - Appelle self._autosize(ws) pour ajuster la largeur des colonnes
      - Retourne self._xlsx_response(wb, "nom_fichier.xlsx")
    """

    def _xlsx_response(self, wb: Workbook, filename: str) -> HttpResponse:
        bio = BytesIO()
        wb.save(bio)
        bio.seek(0)
        resp = HttpResponse(
            bio.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @staticmethod
    def _autosize(ws):
        """
        Ajuste automatiquement la largeur des colonnes en fonction du contenu.
        """
        for col in ws.columns:
            # Longueur max des valeurs de la colonne
            width = max(
                (len(str(c.value)) if c.value is not None else 0)
                for c in col
            ) + 2
            # Limite à 50 pour éviter les colonnes énormes
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(width, 50)

