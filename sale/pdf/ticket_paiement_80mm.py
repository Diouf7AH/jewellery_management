# sale/pdf/ticket_paiement_80mm.py
from decimal import Decimal
from io import BytesIO

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def money(value) -> str:
    try:
        return f"{Decimal(value):,.0f}".replace(",", " ")
    except Exception:
        return "0"


def _truncate(text, max_len=34):
    text = str(text or "")
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def _line_lr(left, right, total_width=42):
    left = str(left or "")
    right = str(right or "")

    if len(right) >= total_width:
        return right[:total_width]

    max_left = total_width - len(right) - 1
    if max_left < 0:
        max_left = 0

    left = left[:max_left]
    free = max(1, total_width - len(left) - len(right))
    return f"{left}{' ' * free}{right}"


def build_ticket_paiement_80mm_pdf(*, facture, paiement):
    """
    Génère un ticket reçu paiement 80mm.
    Retourne un BytesIO.
    """

    buffer = BytesIO()

    vente = getattr(facture, "vente", None)
    client = getattr(vente, "client", None) if vente else None
    bijouterie = getattr(facture, "bijouterie", None)

    paiement_lignes = list(
        paiement.lignes.select_related("mode_paiement").all()
    ) if hasattr(paiement, "lignes") else []

    montant_operation = Decimal("0.00")
    for ligne in paiement_lignes:
        montant_operation += Decimal(getattr(ligne, "montant_paye", 0) or 0)

    total_facture = Decimal(getattr(facture, "montant_total", 0) or 0)
    total_paye = Decimal(getattr(facture, "total_paye", 0) or 0)
    reste = Decimal(getattr(facture, "reste_a_payer", 0) or 0)

    # hauteur dynamique
    base_height_mm = 95
    per_line_mm = 9
    extra_refs_mm = sum(5 for ligne in paiement_lignes if getattr(ligne, "reference", None))
    height = (base_height_mm + len(paiement_lignes) * per_line_mm + extra_refs_mm) * mm

    c = canvas.Canvas(buffer, pagesize=(80 * mm, height))
    width = 80 * mm
    x_left = 3 * mm
    y = height - 5 * mm

    def draw_center(text, size=9, bold=False):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawCentredString(width / 2, y, str(text or ""))
        y -= (size + 3)

    def draw_left(text, size=8, bold=False, mono=False):
        nonlocal y
        if mono:
            font = "Courier-Bold" if bold else "Courier"
        else:
            font = "Helvetica-Bold" if bold else "Helvetica"
        c.setFont(font, size)
        c.drawString(x_left, y, str(text or ""))
        y -= (size + 3)

    def draw_sep():
        nonlocal y
        c.setFont("Courier", 8)
        c.drawString(x_left, y, "-" * 42)
        y -= 10

    # -------------------------
    # HEADER
    # -------------------------
    draw_center("RIO-GOLD", 11, True)
    if bijouterie:
        draw_center(getattr(bijouterie, "nom", "Bijouterie"), 8)
    draw_center("RECU DE PAIEMENT", 9, True)
    draw_sep()

    draw_left(f"FACTURE : {getattr(facture, 'numero_facture', '-')}", 8, True)
    draw_left(f"DATE    : {paiement.date_paiement.strftime('%d/%m/%Y %H:%M')}", 8)

    if vente:
        draw_left(f"VENTE   : {getattr(vente, 'numero_vente', '-')}", 8)

    if client:
        client_name = f"{getattr(client, 'prenom', '')} {getattr(client, 'nom', '')}".strip()
        draw_left(f"CLIENT  : {_truncate(client_name, 28)}", 8)

        tel = getattr(client, "telephone", None)
        if tel:
            draw_left(f"TEL     : {tel}", 8)

    cashier = getattr(paiement, "cashier", None)
    if cashier:
        cashier_name = getattr(cashier, "nom_complet", None) or str(cashier)
        draw_left(f"CAISSIER: {_truncate(cashier_name, 28)}", 8)

    draw_sep()

    # -------------------------
    # MODES DE PAIEMENT
    # -------------------------
    if paiement_lignes:
        draw_left("DETAIL PAIEMENT", 8, True)

        for ligne in paiement_lignes:
            mode_nom = (
                getattr(getattr(ligne, "mode_paiement", None), "nom", None)
                or getattr(getattr(ligne, "mode_paiement", None), "code", None)
                or "Mode"
            )
            montant = f"{money(getattr(ligne, 'montant_paye', 0))} FCFA"
            draw_left(_line_lr(_truncate(mode_nom, 20), montant), 8, mono=True)

            reference = getattr(ligne, "reference", None)
            if reference:
                draw_left(f"REF: {_truncate(reference, 32)}", 7)

        draw_sep()

    # -------------------------
    # TOTAUX
    # -------------------------
    draw_left(_line_lr("MONTANT PAYE", f"{money(montant_operation)} FCFA"), 9, True, True)
    draw_left(_line_lr("TOTAL FACTURE", f"{money(total_facture)} FCFA"), 8, True, True)
    draw_left(_line_lr("TOTAL PAYE", f"{money(total_paye)} FCFA"), 8, True, True)
    draw_left(_line_lr("RESTE A PAYER", f"{money(reste)} FCFA"), 8, True, True)

    draw_sep()

    # -------------------------
    # STATUT
    # -------------------------
    status = getattr(facture, "status", None) or getattr(facture, "statut", None) or "-"
    status_label = str(status).replace("_", " ").upper()
    draw_left(f"STATUT  : {status_label}", 8, True)

    draw_sep()

    # -------------------------
    # FOOTER
    # -------------------------
    draw_center("Merci pour votre confiance !", 8)
    draw_center("Bijouterie Rio-Gold", 8, True)

    c.showPage()
    c.save()

    buffer.seek(0)
    return buffer


    
    
