from decimal import ROUND_HALF_UP, Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)


def money(value):
    value = Decimal(value or 0).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{value:,}".replace(",", " ") + " FCFA"


def build_attestation_rachat_client_pdf(buffer, rachat):
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    title = ParagraphStyle(
        "TitleCustom",
        parent=styles["Title"],
        fontSize=15,
        alignment=1,
        spaceAfter=10,
    )
    center = ParagraphStyle(
        "Center",
        parent=normal,
        alignment=1,
    )

    elements = []

    bijouterie = rachat.bijouterie
    client = rachat.client

    logo = getattr(bijouterie, "logo", None)
    if logo:
        try:
            elements.append(Image(logo.path, width=35 * mm, height=25 * mm))
        except Exception:
            pass

    elements.append(Paragraph(f"<b>{bijouterie}</b>", center))

    adresse_bijouterie = getattr(bijouterie, "adresse", "")
    telephone_bijouterie = getattr(bijouterie, "telephone", "")
    ninea = getattr(bijouterie, "ninea", "")

    elements.append(Paragraph(f"{adresse_bijouterie}", center))
    elements.append(Paragraph(f"Tél : {telephone_bijouterie} | NINEA : {ninea}", center))
    elements.append(Spacer(1, 10))

    elements.append(Paragraph("FICHE D’ATTESTATION DE RACHAT CLIENT", title))
    elements.append(Spacer(1, 8))

    nom_client = str(client)
    adresse_client = rachat.adresse_client
    cni = rachat.cni_client or "________________"
    date_paiement = rachat.paid_at.strftime("%d/%m/%Y") if rachat.paid_at else "________________"

    elements.append(Paragraph(
        f"""
        Je soussigné(e) M./Mme <b>{nom_client}</b>, demeurant à
        <b>{adresse_client}</b>, titulaire de la pièce d’identité N°
        <b>{cni}</b>,
        """,
        normal,
    ))

    elements.append(Spacer(1, 6))

    elements.append(Paragraph(
        f"""
        certifie vendre ce jour le <b>{date_paiement}</b> à la bijouterie
        <b>{bijouterie}</b>, les biens suivants :
        """,
        normal,
    ))

    elements.append(Spacer(1, 10))

    data = [["Description", "Matière", "Pureté", "Poids"]]

    for item in rachat.items.all():
        data.append([
            item.description,
            item.matiere,
            str(item.purete),
            f"{item.poids} g",
        ])

    table = Table(data, colWidths=[75 * mm, 30 * mm, 30 * mm, 30 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 12))

    elements.append(Paragraph(
        f"Pour la somme totale de : <b>{money(rachat.montant_total)}</b>",
        normal,
    ))

    elements.append(Paragraph(
        f"Mode de paiement : <b>{rachat.mode_paiement}</b>",
        normal,
    ))

    elements.append(Spacer(1, 10))

    elements.append(Paragraph(
        """
        Les biens sont vendus en l’état, bien connus de l’acheteur.
        La présente fiche est établie pour servir et valoir ce que de droit.
        """,
        normal,
    ))

    ville = adresse_bijouterie or "________________"
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Fait à <b>{ville}</b>, le <b>{date_paiement}</b>", normal))

    elements.append(Spacer(1, 35))

    signatures = Table([
        ["Signature du vendeur", "Signature de l’acheteur"],
        ["_____________________", "_____________________"],
    ], colWidths=[80 * mm, 80 * mm])

    signatures.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("TOPPADDING", (0, 1), (-1, 1), 20),
    ]))

    elements.append(signatures)

    doc.build(elements)
    


