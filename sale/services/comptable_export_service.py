# sale/services/comptable_export_service.py
from decimal import Decimal

from openpyxl import Workbook


def export_comptable_factures(factures):
    wb = Workbook()
    ws = wb.active
    ws.title = "Journal"

    headers = [
        "Date", "Journal", "Piece", "Compte",
        "Libelle", "Debit", "Credit"
    ]
    ws.append(headers)

    for f in factures:
        date = f.date_creation.strftime("%Y-%m-%d") if getattr(f, "date_creation", None) else ""

        # 1) Ecriture de facture
        ws.append([
            date,
            "VEN",
            f.numero_facture,
            "411",
            "Client",
            float(f.montant_total or 0),
            "",
        ])

        ws.append([
            date,
            "VEN",
            f.numero_facture,
            "701",
            "Vente",
            "",
            float(f.montant_ht or 0),
        ])

        if float(f.montant_tva or 0) > 0:
            ws.append([
                date,
                "VEN",
                f.numero_facture,
                "445",
                "TVA collectée",
                "",
                float(f.montant_tva or 0),
            ])

        # 2) Ecritures de paiement
        for p in f.paiements.all():
            montant_paye = Decimal(p.montant_total_paye or 0)

            if montant_paye <= 0:
                continue

            # Débit caisse / banque
            ws.append([
                date,
                "CAISSE",
                f.numero_facture,
                "571",
                "Caisse",
                montant_paye,
                "",
            ])

            # Crédit client
            ws.append([
                date,
                "CAISSE",
                f.numero_facture,
                "411",
                "Règlement client",
                "",
                montant_paye,
            ])

    return wb
    return wb