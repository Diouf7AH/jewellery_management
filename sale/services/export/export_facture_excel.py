from __future__ import annotations

from decimal import Decimal

from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

ZERO = Decimal("0.00")


def _decimal_value(value) -> Decimal:
    """
    Convertit proprement une valeur monétaire
    en Decimal pour Excel.
    """
    if value is None:
        return ZERO

    if isinstance(value, Decimal):
        return value

    return Decimal(str(value))


def _local_date(value) -> str:
    """
    Retourne une date locale au format JJ/MM/AAAA.
    """
    if not value:
        return ""

    if timezone.is_aware(value):
        value = timezone.localtime(value)

    return value.strftime("%d/%m/%Y")


def _display_value(instance, field_name: str) -> str:
    """
    Utilise get_<field>_display() lorsqu'il existe.
    Sinon retourne directement la valeur du champ.
    """
    if not instance:
        return ""

    display_method = getattr(
        instance,
        f"get_{field_name}_display",
        None,
    )

    if callable(display_method):
        value = display_method()
    else:
        value = getattr(
            instance,
            field_name,
            "",
        )

    return str(value or "")


def export_factures_excel(queryset):
    """
    Exporte un queryset de Facture dans un fichier Excel.

    Le filtrage des factures autorisées doit être effectué
    par la vue avant l'appel de cette fonction.
    """

    # =========================================================
    # WORKBOOK
    # =========================================================

    wb = Workbook()

    ws = wb.active
    ws.title = "Journal des ventes"

    # =========================================================
    # EN-TÊTES
    # =========================================================

    headers = [
        "Numero Facture",
        "Date Facture",
        "Type Facture",
        "Client",
        "Téléphone",
        "Bijouterie",
        "NINEA",
        "Vendeur",
        "Montant HT",
        "TVA",
        "Total TTC",
        "Total Payé",
        "Reste à payer",
        "Statut",
    ]

    ws.append(headers)

    # =========================================================
    # STYLE EN-TÊTES
    # =========================================================

    for cell in ws[1]:
        cell.font = Font(
            bold=True,
        )

        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = (
        f"A1:N1"
    )

    # =========================================================
    # DONNÉES
    # =========================================================

    for facture in queryset:

        # -----------------------------------------------------
        # Vente
        # -----------------------------------------------------

        vente = getattr(
            facture,
            "vente",
            None,
        )

        # -----------------------------------------------------
        # Client
        # -----------------------------------------------------

        client = (
            getattr(
                vente,
                "client",
                None,
            )
            if vente
            else None
        )

        # -----------------------------------------------------
        # Vendeur
        # -----------------------------------------------------

        vendor = (
            getattr(
                vente,
                "vendor",
                None,
            )
            if vente
            else None
        )

        # -----------------------------------------------------
        # Bijouterie
        # -----------------------------------------------------

        bijouterie = getattr(
            facture,
            "bijouterie",
            None,
        )

        # -----------------------------------------------------
        # Nom client
        # -----------------------------------------------------

        if client:
            prenom = (
                getattr(
                    client,
                    "prenom",
                    "",
                )
                or ""
            )

            nom = (
                getattr(
                    client,
                    "nom",
                    "",
                )
                or ""
            )

            client_name = (
                f"{prenom} {nom}"
            ).strip()

            client_phone = (
                getattr(
                    client,
                    "telephone",
                    "",
                )
                or ""
            )

        else:
            client_name = ""
            client_phone = ""

        # -----------------------------------------------------
        # Vendeur
        # -----------------------------------------------------

        vendor_user = (
            getattr(
                vendor,
                "user",
                None,
            )
            if vendor
            else None
        )

        vendor_name = ""

        if vendor_user:
            get_full_name = getattr(
                vendor_user,
                "get_full_name",
                None,
            )

            if callable(get_full_name):
                vendor_name = (
                    get_full_name()
                    or ""
                ).strip()

            if not vendor_name:
                vendor_name = (
                    getattr(
                        vendor_user,
                        "username",
                        "",
                    )
                    or ""
                )

        # -----------------------------------------------------
        # Ligne Excel
        # -----------------------------------------------------

        ws.append([
            facture.numero_facture or "",

            _local_date(
                getattr(
                    facture,
                    "date_creation",
                    None,
                )
            ),

            _display_value(
                facture,
                "type_facture",
            ),

            client_name,

            client_phone,

            (
                getattr(
                    bijouterie,
                    "nom",
                    "",
                )
                or ""
            ),

            (
                getattr(
                    bijouterie,
                    "ninea",
                    "",
                )
                or ""
            ),

            vendor_name,

            _decimal_value(
                getattr(
                    facture,
                    "montant_ht",
                    ZERO,
                )
            ),

            _decimal_value(
                getattr(
                    facture,
                    "montant_tva",
                    ZERO,
                )
            ),

            _decimal_value(
                getattr(
                    facture,
                    "montant_total",
                    ZERO,
                )
            ),

            _decimal_value(
                getattr(
                    facture,
                    "total_paye",
                    ZERO,
                )
            ),

            _decimal_value(
                getattr(
                    facture,
                    "reste_a_payer",
                    ZERO,
                )
            ),

            _display_value(
                facture,
                "status",
            ),
        ])

    # =========================================================
    # FORMAT DES MONTANTS
    # =========================================================

    money_columns = (
        "I",
        "J",
        "K",
        "L",
        "M",
    )

    for column in money_columns:
        for cell in ws[column][1:]:
            cell.number_format = '#,##0.00'

    # =========================================================
    # ALIGNEMENT
    # =========================================================

    for row in ws.iter_rows(
        min_row=2,
    ):
        for cell in row:
            cell.alignment = Alignment(
                vertical="center",
            )

    # =========================================================
    # LARGEUR DES COLONNES
    # =========================================================

    column_widths = {
        "A": 24,  # Numéro facture
        "B": 14,  # Date
        "C": 18,  # Type
        "D": 28,  # Client
        "E": 18,  # Téléphone
        "F": 24,  # Bijouterie
        "G": 20,  # NINEA
        "H": 24,  # Vendeur
        "I": 16,  # HT
        "J": 16,  # TVA
        "K": 16,  # TTC
        "L": 16,  # Payé
        "M": 16,  # Reste
        "N": 16,  # Statut
    }

    for column, width in column_widths.items():
        ws.column_dimensions[
            column
        ].width = width

    # =========================================================
    # HAUTEUR EN-TÊTE
    # =========================================================

    ws.row_dimensions[1].height = 22

    # =========================================================
    # RÉPONSE
    # =========================================================

    response = HttpResponse(
        content_type=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        )
    )

    response[
        "Content-Disposition"
    ] = (
        'attachment; '
        'filename="journal_ventes.xlsx"'
    )

    wb.save(response)

    return response


