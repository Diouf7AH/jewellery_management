# sale/services/export/export_facture_excel.py
from django.http import HttpResponse
from django.utils.timezone import localtime
from openpyxl import Workbook


def export_factures_excel(queryset):
    wb = Workbook()
    ws = wb.active
    ws.title = "Journal des ventes"

    ws.append([
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
    ])

    for f in queryset:
        vente = getattr(f, "vente", None)
        client = getattr(vente, "client", None) if vente else None
        vendor = getattr(vente, "vendor", None) if vente else None
        bij = getattr(f, "bijouterie", None)

        ws.append([
            f.numero_facture,
            localtime(f.date_creation).strftime("%d/%m/%Y") if getattr(f, "date_creation", None) else "",
            f.type_facture,
            f"{client.prenom} {client.nom}" if client else "",
            client.telephone if client else "",
            bij.nom if bij else "",
            bij.ninea if bij else "",
            vendor.user.username if vendor and getattr(vendor, "user", None) else "",
            float(f.montant_ht or 0),
            float(f.montant_tva or 0),
            float(f.montant_total or 0),
            float(f.total_paye or 0),
            float(f.reste_a_payer or 0),
            f.status,
        ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="journal_ventes.xlsx"'
    wb.save(response)
    return response

