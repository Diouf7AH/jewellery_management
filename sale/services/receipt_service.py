# sale/services/receipt_service.py

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from sale.models import PaiementLigne, VenteAutre, VenteProduit
from sale.services.pdf_amount_validation import validate_pdf_amount

ZERO = Decimal("0.00")

TICKET_WIDTH = 80 * mm
TICKET_MARGIN = 4 * mm
CONTENT_WIDTH = TICKET_WIDTH - (2 * TICKET_MARGIN)

MIN_TICKET_HEIGHT = 80 * mm
TOP_MARGIN = 6 * mm
BOTTOM_MARGIN = 6 * mm

LINE_SPACING = 4


# ============================================================
# 1. HELPERS
# ============================================================

def _safe_text(value) -> str:
    """
    Convertit une valeur facultative en texte.
    """

    if value is None:
        return ""

    return str(value).strip()


def _money(value) -> str:
    """
    Formate un montant en FCFA.
    """

    montant = validate_pdf_amount(
        value,
        "montant",
    )

    return f"{montant:,.2f} FCFA".replace(",", " ")


def _date_locale(value):
    """
    Convertit une date dans le fuseau local.
    """

    if value is None:
        raise ValueError(
            "La date du paiement est manquante."
        )

    if timezone.is_aware(value):
        return timezone.localtime(value)

    return value


def _nom_client(client) -> str:
    """
    Retourne le nom et éventuellement
    le téléphone du client.
    """

    if client is None:
        return ""

    prenom = _safe_text(
        getattr(client, "prenom", "")
    )

    nom = _safe_text(
        getattr(client, "nom", "")
    )

    telephone = _safe_text(
        getattr(client, "telephone", "")
    )

    client_nom = f"{prenom} {nom}".strip()

    if telephone:
        if client_nom:
            client_nom += f" | Tel: {telephone}"
        else:
            client_nom = f"Tel: {telephone}"

    return client_nom


def _nom_caissier(paiement) -> str:
    """
    Recherche le nom du caissier.

    Priorité :
        - paiement.cashier ;
        - paiement.created_by.
    """

    cashier = getattr(
        paiement,
        "cashier",
        None,
    )

    if cashier is not None:
        user = getattr(
            cashier,
            "user",
            None,
        )

    else:
        user = getattr(
            paiement,
            "created_by",
            None,
        )

    if user is None:
        return ""

    full_name = ""

    if hasattr(user, "get_full_name"):
        full_name = _safe_text(
            user.get_full_name()
        )

    return (
        full_name
        or _safe_text(
            getattr(user, "email", "")
        )
        or _safe_text(user)
    )


# ============================================================
# 2. DÉCOUPAGE DES TEXTES
# ============================================================

def _decouper_mot_long(
    mot: str,
    font_name: str,
    font_size: int,
) -> list[str]:
    """
    Découpe les mots et références trop longs
    pour la largeur du ticket.
    """

    morceaux = []
    courant = ""

    for caractere in mot:

        proposition = courant + caractere

        if stringWidth(
            proposition,
            font_name,
            font_size,
        ) <= CONTENT_WIDTH:

            courant = proposition

        else:

            if courant:
                morceaux.append(courant)

            courant = caractere

    if courant:
        morceaux.append(courant)

    return morceaux


def _decouper_texte(
    texte: str,
    taille: int,
    gras: bool,
) -> list[tuple]:
    """
    Découpe un texte en lignes imprimables
    sans dépasser les 72 mm disponibles.
    """

    font_name = (
        "Helvetica-Bold"
        if gras
        else "Helvetica"
    )

    mots = _safe_text(texte).split()

    if not mots:
        return []

    lignes = []
    courant = ""

    for mot in mots:

        proposition = (
            f"{courant} {mot}".strip()
        )

        if stringWidth(
            proposition,
            font_name,
            taille,
        ) <= CONTENT_WIDTH:

            courant = proposition
            continue

        if courant:
            lignes.append((
                courant,
                taille,
                gras,
            ))

            courant = ""

        if stringWidth(
            mot,
            font_name,
            taille,
        ) <= CONTENT_WIDTH:

            courant = mot

        else:

            morceaux = _decouper_mot_long(
                mot,
                font_name,
                taille,
            )

            for morceau in morceaux[:-1]:
                lignes.append((
                    morceau,
                    taille,
                    gras,
                ))

            if morceaux:
                courant = morceaux[-1]

    if courant:
        lignes.append((
            courant,
            taille,
            gras,
        ))

    return lignes


# ============================================================
# 3. CONSTRUCTION DU CONTENU
# ============================================================

def _construire_contenu(
    *,
    paiement,
    vente,
    facture,
    bijouterie,
    paiement_lignes,
    montant_operation,
    montant_total,
    total_paye,
    reste_a_payer,
    libelle_total,
) -> list[tuple]:
    """
    Prépare le contenu du ticket thermique.

    Chaque élément :
        (texte, taille_police, gras)
    """

    date_paiement = _date_locale(
        getattr(
            paiement,
            "date_paiement",
            None,
        )
    )

    date_txt = date_paiement.strftime(
        "%d/%m/%Y %H:%M"
    )

    bij_nom = (
        _safe_text(
            getattr(
                bijouterie,
                "nom",
                "",
            )
        )
        or "Bijouterie Rio-Gold"
    )

    bij_tel = (
        _safe_text(
            getattr(
                bijouterie,
                "telephone_portable_1",
                "",
            )
        )
        or _safe_text(
            getattr(
                bijouterie,
                "telephone_fix",
                "",
            )
        )
        or _safe_text(
            getattr(
                settings,
                "RIOGOLD_PHONE",
                "",
            )
        )
    )

    bij_addr = (
        _safe_text(
            getattr(
                bijouterie,
                "adresse",
                "",
            )
        )
        or _safe_text(
            getattr(
                settings,
                "RIOGOLD_ADDRESS",
                "",
            )
        )
    )

    client_nom = _nom_client(
        getattr(
            vente,
            "client",
            None,
        )
    )

    cashier_nom = _nom_caissier(
        paiement
    )

    numero_vente = _safe_text(
        getattr(
            vente,
            "numero_vente",
            "",
        )
    )

    numero_facture = (
        _safe_text(
            getattr(
                facture,
                "numero_facture",
                "",
            )
        )
        if facture is not None
        else ""
    )

    contenu = [
        ("RIO-GOLD", 11, True),
        (bij_nom, 9, True),
    ]

    if bij_addr:
        contenu.append((
            f"Adresse: {bij_addr}",
            7,
            False,
        ))

    if bij_tel:
        contenu.append((
            f"Telephone: {bij_tel}",
            7,
            False,
        ))

    contenu.extend([
        ("-", 8, False),
        ("RECU DE PAIEMENT", 10, True),
        ("-", 8, False),
        (f"Date: {date_txt}", 8, False),
        (f"Paiement N: {paiement.pk}", 8, False),
    ])

    if numero_facture:
        contenu.append((
            f"Facture: {numero_facture}",
            8,
            False,
        ))

    if numero_vente:
        contenu.append((
            f"Vente: {numero_vente}",
            8,
            False,
        ))

    if client_nom:
        contenu.append((
            f"Client: {client_nom}",
            8,
            False,
        ))

    if cashier_nom:
        contenu.append((
            f"Caissier: {cashier_nom}",
            8,
            False,
        ))

    contenu.extend([
        ("-", 8, False),
        ("DETAIL DU PAIEMENT", 9, True),
    ])

    for ligne in paiement_lignes:

        mode = getattr(
            ligne,
            "mode_paiement",
            None,
        )

        mode_nom = (
            _safe_text(
                getattr(mode, "nom", "")
            )
            or _safe_text(
                getattr(mode, "code", "")
            )
            or "Mode"
        )

        montant = validate_pdf_amount(
            ligne.montant_paye,
            "montant_paye",
        )

        contenu.append((
            f"{mode_nom}: {_money(montant)}",
            8,
            False,
        ))

        reference = _safe_text(
            getattr(
                ligne,
                "reference",
                "",
            )
        )

        if reference:
            contenu.append((
                f"Reference: {reference}",
                7,
                False,
            ))

    contenu.extend([
        ("-", 8, False),

        (
            f"Montant operation: "
            f"{_money(montant_operation)}",
            8,
            True,
        ),

        (
            f"{libelle_total}: "
            f"{_money(montant_total)}",
            8,
            False,
        ),

        (
            f"Total paye: "
            f"{_money(total_paye)}",
            8,
            False,
        ),

        (
            f"Reste a payer: "
            f"{_money(reste_a_payer)}",
            8,
            True,
        ),

        ("-", 8, False),

        (
            "Merci pour votre confiance",
            8,
            False,
        ),

        ("Rio-Gold", 8, True),
    ])

    return contenu


# ============================================================
# 4. GÉNÉRATION DU TICKET THERMIQUE
# ============================================================

def _generer_pdf_80mm(
    contenu: list[tuple],
) -> bytes:
    """
    Génère le PDF thermique 80 mm.

    La hauteur est calculée selon
    le contenu du reçu.
    """

    lignes_pdf = []

    for texte, taille, gras in contenu:

        if texte == "-":
            lignes_pdf.append((
                "-",
                taille,
                gras,
            ))

        else:
            lignes_pdf.extend(
                _decouper_texte(
                    texte,
                    taille,
                    gras,
                )
            )

    hauteur_contenu = sum(
        (
            10
            if texte == "-"
            else taille + LINE_SPACING
        )
        for texte, taille, _ in lignes_pdf
    )

    ticket_height = max(
        MIN_TICKET_HEIGHT,
        hauteur_contenu
        + TOP_MARGIN
        + BOTTOM_MARGIN,
    )

    buffer = BytesIO()

    try:
        pdf = canvas.Canvas(
            buffer,
            pagesize=(
                TICKET_WIDTH,
                ticket_height,
            ),
        )

        y = ticket_height - TOP_MARGIN

        for texte, taille, gras in lignes_pdf:

            if texte == "-":

                pdf.setLineWidth(0.5)

                pdf.line(
                    TICKET_MARGIN,
                    y,
                    TICKET_WIDTH - TICKET_MARGIN,
                    y,
                )

                y -= 10
                continue

            font_name = (
                "Helvetica-Bold"
                if gras
                else "Helvetica"
            )

            pdf.setFont(
                font_name,
                taille,
            )

            pdf.drawString(
                TICKET_MARGIN,
                y,
                texte,
            )

            y -= taille + LINE_SPACING

        pdf.showPage()
        pdf.save()

        pdf_bytes = buffer.getvalue()

    finally:
        buffer.close()

    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError(
            "La génération du reçu PDF a échoué."
        )

    return pdf_bytes


# ============================================================
# 5. SERVICE PRINCIPAL
# ============================================================

def generate_recu_paiement_pdf_bytes(
    *,
    paiement,
) -> bytes:
    """
    Génère un reçu PDF thermique 80 mm.

    Compatible avec :
        - bijoux uniquement ;
        - bijoux + prestations ;
        - prestations uniquement.

    Règles :
        - un reçu par opération de paiement ;
        - aucune facture pour prestations seules ;
        - aucun mouvement de stock ;
        - aucune modification de paiement ;
        - aucun fichier enregistré.

    Retour :
        bytes du PDF.
    """

    # ========================================================
    # 1. VALIDATION DU PAIEMENT
    # ========================================================

    if (
        paiement is None
        or getattr(paiement, "pk", None) is None
    ):
        raise ValueError(
            "Paiement enregistré obligatoire."
        )

    # ========================================================
    # 2. FACTURE ET VENTE
    # ========================================================

    facture = getattr(
        paiement,
        "facture",
        None,
    )

    vente = getattr(
        paiement,
        "vente",
        None,
    )

    if vente is None and facture is not None:
        vente = getattr(
            facture,
            "vente",
            None,
        )

    if vente is None:
        raise ValueError(
            "Le paiement doit être associé "
            "à une vente."
        )

    if (
        facture is not None
        and facture.vente_id != vente.pk
    ):
        raise ValueError(
            "La facture et la vente "
            "ne correspondent pas."
        )

    # ========================================================
    # 3. BIJOUTERIE
    # ========================================================

    bijouterie = getattr(
        vente,
        "bijouterie",
        None,
    )

    if bijouterie is None:
        raise ValueError(
            "Bijouterie introuvable."
        )

    if (
        facture is not None
        and facture.bijouterie_id
        != vente.bijouterie_id
    ):
        raise ValueError(
            "La facture et la vente appartiennent "
            "à des bijouteries différentes."
        )

    # ========================================================
    # 4. TYPE DE VENTE
    # ========================================================

    contient_bijoux = (
        VenteProduit.objects
        .filter(vente_id=vente.pk)
        .exists()
    )

    contient_prestations = (
        VenteAutre.objects
        .filter(vente_id=vente.pk)
        .exists()
    )

    if (
        not contient_bijoux
        and not contient_prestations
    ):
        raise ValueError(
            "La vente ne contient "
            "aucune ligne."
        )

    if contient_bijoux and facture is None:
        raise ValueError(
            "Une vente contenant des bijoux "
            "doit être associée à une facture."
        )

    if (
        not contient_bijoux
        and facture is not None
    ):
        raise ValueError(
            "Une vente contenant uniquement "
            "des prestations ne doit pas "
            "posséder de facture."
        )

    # ========================================================
    # 5. LIGNES DU PAIEMENT
    # ========================================================

    paiement_lignes = list(
        PaiementLigne.objects
        .filter(
            paiement_id=paiement.pk
        )
        .select_related(
            "mode_paiement"
        )
        .order_by("pk")
    )

    if not paiement_lignes:
        raise ValueError(
            "Aucune ligne de paiement enregistrée."
        )

    if (
        not contient_bijoux
        and len(paiement_lignes) != 1
    ):
        raise ValueError(
            "Un paiement direct de prestation "
            "doit contenir exactement "
            "un mode de paiement."
        )

    # ========================================================
    # 6. MONTANT DE L'OPÉRATION
    # ========================================================

    montant_operation = sum(
        (
            validate_pdf_amount(
                ligne.montant_paye,
                "montant_paye",
            )
            for ligne in paiement_lignes
        ),
        ZERO,
    )

    if montant_operation <= ZERO:
        raise ValueError(
            "Le montant de l'opération "
            "doit être strictement positif."
        )

    # ========================================================
    # 7. TOTAL ET SOLDE
    # ========================================================

    if facture is not None:

        montant_total = validate_pdf_amount(
            facture.montant_total,
            "montant_total",
        )

        total_paye = validate_pdf_amount(
            facture.total_paye,
            "total_paye",
        )

        reste_a_payer = validate_pdf_amount(
            facture.reste_a_payer,
            "reste_a_payer",
        )

        libelle_total = "Total facture"

    else:

        montant_total = validate_pdf_amount(
            vente.montant_total,
            "montant_total",
        )

        total_paye_brut = (
            PaiementLigne.objects
            .filter(
                paiement__vente_id=vente.pk,
                paiement__facture__isnull=True,
            )
            .aggregate(
                total=Sum("montant_paye")
            )["total"]
            or ZERO
        )

        total_paye = validate_pdf_amount(
            total_paye_brut,
            "total_paye",
        )

        if total_paye > montant_total:
            raise ValueError(
                "Le total payé dépasse "
                "le montant de la prestation."
            )

        reste_a_payer = (
            montant_total - total_paye
        )

        libelle_total = "Total prestation"

    # ========================================================
    # 8. COHÉRENCE FINANCIÈRE
    # ========================================================

    if total_paye > montant_total:
        raise ValueError(
            "Le total payé dépasse "
            "le montant de la vente."
        )

    if (
        montant_total - total_paye
        != reste_a_payer
    ):
        raise ValueError(
            "Incohérence entre le montant total, "
            "le total payé et le reste à payer."
        )

    # ========================================================
    # 9. CONSTRUCTION DU CONTENU
    # ========================================================

    contenu = _construire_contenu(
        paiement=paiement,
        vente=vente,
        facture=facture,
        bijouterie=bijouterie,
        paiement_lignes=paiement_lignes,
        montant_operation=montant_operation,
        montant_total=montant_total,
        total_paye=total_paye,
        reste_a_payer=reste_a_payer,
        libelle_total=libelle_total,
    )

    # ========================================================
    # 10. PDF THERMIQUE 80 MM
    # ========================================================

    return _generer_pdf_80mm(
        contenu
    )

