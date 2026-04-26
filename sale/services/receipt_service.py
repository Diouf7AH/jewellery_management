# sale/services/receipt_service.py
from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.utils import timezone
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def _money(value: Decimal) -> str:
    value = Decimal(str(value or "0"))
    return f"{value:,.2f} FCFA".replace(",", " ")


def generate_recu_paiement_pdf_bytes(*, paiement) -> bytes:
    """
    Génère un reçu PDF pour une opération Paiement.
    Ne stocke rien. Retourne les bytes du PDF.
    """

    facture = getattr(paiement, "facture", None)
    if not facture:
        return b""

    vente = getattr(facture, "vente", None)
    bij = getattr(facture, "bijouterie", None)
    client = getattr(vente, "client", None) if vente else None
    cashier = getattr(paiement, "cashier", None)

    paiement_lignes = list(
        paiement.lignes.select_related("mode_paiement").all().order_by("id")
    )

    numero_facture = getattr(facture, "numero_facture", "") or ""
    numero_vente = getattr(vente, "numero_vente", "") if vente else ""
    date_txt = timezone.localtime(
        getattr(paiement, "date_paiement", timezone.now())
    ).strftime("%d/%m/%Y %H:%M")

    bij_nom = getattr(bij, "nom", "Bijouterie Rio-Gold") or "Bijouterie Rio-Gold"
    bij_tel = (
        getattr(bij, "telephone_portable_1", None)
        or getattr(bij, "telephone", None)
        or getattr(settings, "RIOGOLD_PHONE", "")
    )
    bij_addr = getattr(bij, "adresse", None) or getattr(settings, "RIOGOLD_ADDRESS", "")

    client_nom = ""
    if client:
        nom = (getattr(client, "nom", "") or "").strip()
        prenom = (getattr(client, "prenom", "") or "").strip()
        tel = (getattr(client, "telephone", "") or "").strip()
        client_nom = f"{prenom} {nom}".strip()
        if tel:
            client_nom = f"{client_nom} | Tel: {tel}".strip(" |")

    cashier_nom = ""
    if cashier:
        cashier_user = getattr(cashier, "user", None)
        if cashier_user:
            full = f"{getattr(cashier_user, 'first_name', '')} {getattr(cashier_user, 'last_name', '')}".strip()
            cashier_nom = full or str(cashier)
        else:
            cashier_nom = str(cashier)

    montant_operation = paiement.montant_total_paye
    total_facture = getattr(facture, "montant_total", Decimal("0.00")) or Decimal("0.00")
    total_paye = getattr(facture, "total_paye", Decimal("0.00")) or Decimal("0.00")
    reste_a_payer = getattr(facture, "reste_a_payer", Decimal("0.00")) or Decimal("0.00")

    width = 80 * mm
    base_height = 110 * mm
    extra_per_line = 8 * mm
    height = base_height + (len(paiement_lignes) * extra_per_line)

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))

    x = 4 * mm
    y = height - 6 * mm

    def draw(text, size=8, bold=False):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(x, y, str(text))
        y -= (size + 3)

    def draw_sep():
        nonlocal y
        c.setFont("Helvetica", 8)
        c.drawString(x, y, "-" * 42)
        y -= 10

    draw("RIO-GOLD", 11, True)
    draw(bij_nom, 9, True)

    if bij_addr:
        draw(f"Adresse: {bij_addr}", 7)
    if bij_tel:
        draw(f"Telephone: {bij_tel}", 7)

    draw_sep()
    draw("RECU DE PAIEMENT", 10, True)
    draw_sep()

    draw(f"Date: {date_txt}", 8)
    draw(f"Facture: {numero_facture}", 8)

    if numero_vente:
        draw(f"Vente: {numero_vente}", 8)

    if client_nom:
        draw(f"Client: {client_nom}", 8)

    if cashier_nom:
        draw(f"Caissier: {cashier_nom}", 8)

    draw_sep()
    draw("DETAIL PAIEMENT", 9, True)

    if paiement_lignes:
        for ligne in paiement_lignes:
            mode = getattr(ligne, "mode_paiement", None)
            mode_label = getattr(mode, "nom", None) or getattr(mode, "code", None) or "Mode"
            montant = getattr(ligne, "montant_paye", Decimal("0.00")) or Decimal("0.00")

            draw(f"{mode_label}: {_money(montant)}", 8)

            reference = getattr(ligne, "reference", None)
            if reference:
                draw(f"Ref: {reference}", 7)
    else:
        draw("Aucune ligne de paiement", 8)

    draw_sep()
    draw(f"Montant operation: {_money(montant_operation)}", 8, True)
    draw(f"Total facture: {_money(total_facture)}", 8)
    draw(f"Total paye: {_money(total_paye)}", 8)
    draw(f"Reste a payer: {_money(reste_a_payer)}", 8)
    draw_sep()
    draw("Merci pour votre confiance", 8)
    draw("Rio-Gold", 8, True)

    c.showPage()
    c.save()

    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

