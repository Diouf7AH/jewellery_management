# sale/services/facture_pdf_data_service.py

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.utils import timezone

from sale.services.montant_service import calculer_solde_paiement

ZERO = Decimal("0.00")
TWOPLACES = Decimal("0.01")
HUNDRED = Decimal("100")


# ============================================================
# VALIDATION DES VALEURS
# ============================================================

def validate_pdf_amount(
    value,
    field_name: str,
    *,
    allow_negative: bool = False,
) -> Decimal:
    """
    Valide une valeur Decimal avant génération du PDF.

    - Refuse None et les chaînes vides.
    - Refuse les booléens.
    - Refuse NaN et Infinity.
    - Refuse les valeurs négatives par défaut.
    - N'effectue aucun arrondi.
    """

    if value is None or (
        isinstance(value, str) and not value.strip()
    ):
        raise ValueError(
            f"La valeur '{field_name}' est manquante."
        )

    if isinstance(value, bool):
        raise ValueError(
            f"La valeur '{field_name}' est invalide."
        )

    try:
        montant = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(
            f"La valeur '{field_name}' est invalide."
        ) from exc

    if not montant.is_finite():
        raise ValueError(
            f"La valeur '{field_name}' doit être finie."
        )

    if not allow_negative and montant < ZERO:
        raise ValueError(
            f"La valeur '{field_name}' ne peut pas être négative."
        )

    return montant


def validate_pdf_quantity(
    value,
    field_name: str,
) -> Decimal:
    """
    Valide une quantité strictement positive.
    """

    quantite = validate_pdf_amount(
        value,
        field_name,
    )

    if quantite <= ZERO:
        raise ValueError(
            f"La quantité '{field_name}' doit être positive."
        )

    return quantite


def validate_pdf_percentage(
    value,
    field_name: str,
) -> Decimal:
    """
    Valide un pourcentage compris entre 0 et 100.
    """

    pourcentage = validate_pdf_amount(
        value,
        field_name,
    )

    if pourcentage > HUNDRED:
        raise ValueError(
            f"Le pourcentage '{field_name}' ne peut pas dépasser 100 %."
        )

    return pourcentage


def round_pdf_money(value: Decimal) -> Decimal:
    """
    Arrondit à deux décimales comme Facture.recalculer_totaux().
    """

    try:
        return value.quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )
    except InvalidOperation as exc:
        raise ValueError(
            "Montant financier hors limites."
        ) from exc


# ============================================================
# CONSTRUCTION DES DONNÉES DE FACTURE PDF
# ============================================================

def build_facture_pdf_data(facture) -> dict:
    """
    Construit les données nécessaires au PDF de facture Rio-Gold.

    Ventes autorisées :
        - bijoux uniquement ;
        - bijoux + prestations.

    Ventes interdites :
        - prestations uniquement.

    Les ventes de prestations seules utilisent
    le paiement direct et un reçu de paiement.

    Ce service ne modifie :
        - ni la facture ;
        - ni les paiements ;
        - ni les stocks.
    """

    # ========================================================
    # 1. VALIDATION FACTURE / VENTE
    # ========================================================

    if facture is None:
        raise ValueError(
            "Aucune facture fournie."
        )

    vente = getattr(
        facture,
        "vente",
        None,
    )

    if vente is None:
        raise ValueError(
            "Impossible de générer la facture : "
            "aucune vente associée."
        )

    if not vente.lignes.exists():
        raise ValueError(
            "Impossible de générer une facture : "
            "la vente ne contient aucun bijou. "
            "Les prestations seules nécessitent "
            "un paiement direct avec reçu."
        )

    if facture.bijouterie_id != vente.bijouterie_id:
        raise ValueError(
            "La bijouterie de la facture "
            "ne correspond pas à celle de la vente."
        )

    if facture.type_facture not in (
        facture.TYPE_PROFORMA,
        facture.TYPE_FACTURE,
    ):
        raise ValueError(
            "Type de facture non autorisé "
            "pour ce générateur PDF."
        )

    bijouterie = facture.bijouterie
    client = getattr(vente, "client", None)

    # ========================================================
    # 2. VALIDATION DES MONTANTS
    # ========================================================

    total_ht = validate_pdf_amount(
        facture.montant_ht,
        "facture.montant_ht",
    )

    frais_transaction = validate_pdf_amount(
        facture.frais_transaction,
        "facture.frais_transaction",
    )

    appliquer_tva = facture.appliquer_tva

    # --------------------------------------------------------
    # TVA
    # --------------------------------------------------------

    if appliquer_tva:

        taux_tva = validate_pdf_percentage(
            facture.taux_tva,
            "facture.taux_tva",
        )

        montant_tva = validate_pdf_amount(
            facture.montant_tva,
            "facture.montant_tva",
        )

        tva_attendue = round_pdf_money(
            total_ht * taux_tva / HUNDRED
        )

        if montant_tva != tva_attendue:
            raise ValueError(
                "Incohérence financière : "
                "le montant TVA ne correspond pas "
                "au montant HT et au taux de TVA."
            )

    else:

        taux_tva = None
        montant_tva = None

        if facture.taux_tva is not None:
            raise ValueError(
                "La TVA est désactivée, "
                "mais un taux de TVA est renseigné."
            )

        if facture.montant_tva is not None:
            raise ValueError(
                "La TVA est désactivée, "
                "mais un montant TVA est renseigné."
            )

    # --------------------------------------------------------
    # TOTAL TTC
    # --------------------------------------------------------

    total_ttc = validate_pdf_amount(
        facture.montant_total,
        "facture.montant_total",
    )

    total_attendu = round_pdf_money(
        total_ht
        + (
            montant_tva
            if montant_tva is not None
            else ZERO
        )
        + frais_transaction
    )

    if total_ttc != total_attendu:
        raise ValueError(
            "Incohérence financière : "
            "montant HT + TVA + frais de transaction "
            "ne correspond pas au montant total."
        )

    # ========================================================
    # 3. VALIDATION DES PAIEMENTS
    # ========================================================

    amount_paid = validate_pdf_amount(
        facture.total_paye,
        "facture.total_paye",
    )

    # Le service métier vérifie :
    # - les montants négatifs ;
    # - la précision de deux décimales ;
    # - les trop-perçus ;
    # - le solde exact.

    try:

        solde = calculer_solde_paiement(
            montant_total=total_ttc,
            montant_deja_paye=amount_paid,
        )

    except ValidationError as exc:
        raise ValueError(
            "Impossible de générer la facture PDF : "
            "les paiements enregistrés sont incohérents. "
            f"{exc}"
        ) from exc

    remaining_amount = solde["reste_a_payer"]

    # Aucune seconde formule de paiement :
    # calculer_solde_paiement() est la source de vérité.

    # ========================================================
    # 4. LIGNES DE BIJOUX
    # ========================================================

    lines = []

    lignes_bijoux = (
        vente.lignes
        .select_related(
            "produit_line__produit",
        )
        .all()
    )

    for vp in lignes_bijoux:

        produit_line = getattr(
            vp,
            "produit_line",
            None,
        )

        if produit_line is None:
            raise ValueError(
                f"La ligne bijou {vp.pk} "
                "ne possède pas de ProduitLine."
            )

        produit = getattr(
            produit_line,
            "produit",
            None,
        )

        if produit is None:
            raise ValueError(
                f"La ligne bijou {vp.pk} "
                "ne possède pas de produit."
            )

        produit_nom = (
            getattr(produit, "nom", None)
            or "Produit non renseigné"
        )

        # ----------------------------------------------------
        # Poids
        # ----------------------------------------------------

        poids_valeur = getattr(
            produit,
            "poids",
            None,
        )

        if poids_valeur is not None:

            poids = str(
                validate_pdf_amount(
                    poids_valeur,
                    f"bijou {vp.pk}.poids",
                )
            )

        else:
            poids = ""

        # ----------------------------------------------------
        # Pureté
        # ----------------------------------------------------

        purete = ""

        purete_obj = getattr(
            produit,
            "purete",
            None,
        )

        if purete_obj is not None:

            purete = (
                getattr(purete_obj, "purete", None)
                or getattr(purete_obj, "nom", None)
                or str(purete_obj)
            )

        # ----------------------------------------------------
        # État du bijou
        # ----------------------------------------------------

        if hasattr(
            produit,
            "get_etat_display",
        ):

            etat = (
                produit.get_etat_display()
                or ""
            )

        else:

            etat = (
                getattr(produit, "etat", "")
                or ""
            )

        # ----------------------------------------------------
        # Montants de la ligne
        # ----------------------------------------------------

        quantite = validate_pdf_quantity(
            vp.quantite,
            f"bijou {vp.pk}.quantite",
        )

        prix_gramme = validate_pdf_amount(
            vp.prix_vente_grammes,
            f"bijou {vp.pk}.prix_vente_grammes",
        )

        montant_ht_ligne = validate_pdf_amount(
            vp.montant_ht,
            f"bijou {vp.pk}.montant_ht",
        )

        montant_total_ligne = validate_pdf_amount(
            vp.montant_total,
            f"bijou {vp.pk}.montant_total",
        )

        # ----------------------------------------------------
        # Réduction occasion
        # ----------------------------------------------------

        if vp.pourcentage_occasion is None:

            pourcentage_occasion = ZERO

        else:

            pourcentage_occasion = validate_pdf_percentage(
                vp.pourcentage_occasion,
                f"bijou {vp.pk}.pourcentage_occasion",
            )

        reduction_occasion = ZERO

        if getattr(
            produit,
            "etat",
            None,
        ) == "O":

            reduction_occasion = round_pdf_money(
                montant_ht_ligne
                * pourcentage_occasion
                / HUNDRED
            )

        # ----------------------------------------------------
        # Données PDF
        # ----------------------------------------------------

        lines.append({
            "type_ligne": "bijou",
            "label": produit_nom,
            "poids": poids,
            "qty": quantite,
            "prix_gramme": prix_gramme,
            "prix_unitaire": ZERO,
            "total": montant_total_ligne,
            "purete": purete,
            "etat": etat,
            "pourcentage_occasion": pourcentage_occasion,
            "reduction_occasion": reduction_occasion,
        })

    # ========================================================
    # 5. PRESTATIONS
    # ========================================================

    for autre in vente.autres.all():

        designation = (
            autre.get_type_autre_display()
        )

        quantite = validate_pdf_quantity(
            autre.quantite,
            f"prestation {autre.pk}.quantite",
        )

        prix_unitaire = validate_pdf_amount(
            autre.prix_unitaire,
            f"prestation {autre.pk}.prix_unitaire",
        )

        montant_total_ligne = validate_pdf_amount(
            autre.montant_total,
            f"prestation {autre.pk}.montant_total",
        )

        lines.append({
            "type_ligne": "prestation",
            "label": designation,
            "poids": "",
            "qty": quantite,
            "prix_gramme": ZERO,
            "prix_unitaire": prix_unitaire,
            "total": montant_total_ligne,
            "purete": "",
            "etat": "",
            "pourcentage_occasion": ZERO,
            "reduction_occasion": ZERO,
        })

    # ========================================================
    # 6. INFORMATIONS BIJOUTERIE
    # ========================================================

    shop_name = (
        getattr(
            bijouterie,
            "nom",
            None,
        )
        or "RIO GOLD"
    )

    shop_phone = (
        getattr(
            bijouterie,
            "telephone_portable_1",
            None,
        )
        or getattr(
            bijouterie,
            "telephone_portable_2",
            None,
        )
        or getattr(
            bijouterie,
            "telephone_fix",
            None,
        )
        or ""
    )

    shop_ninea = (
        getattr(
            bijouterie,
            "ninea",
            None,
        )
        or getattr(
            bijouterie,
            "ninenea",
            None,
        )
        or ""
    )

    shop_address = (
        getattr(
            bijouterie,
            "adresse",
            "",
        )
        or ""
    )

    # ========================================================
    # 7. INFORMATIONS CLIENT
    # ========================================================

    client_name = ""
    client_phone = ""
    client_address = ""

    if client:

        client_name = (
            f"{getattr(client, 'prenom', '') or ''} "
            f"{getattr(client, 'nom', '') or ''}"
        ).strip()

        client_phone = (
            getattr(
                client,
                "telephone",
                "",
            )
            or ""
        )

        client_address = (
            getattr(
                client,
                "adresse",
                "",
            )
            or ""
        )

    # ========================================================
    # 8. VENDEUR
    # ========================================================

    vendor_name = ""

    vendor = getattr(
        vente,
        "vendor",
        None,
    )

    if vendor:

        vendor_user = getattr(
            vendor,
            "user",
            None,
        )

        if vendor_user:

            full_name = ""

            if hasattr(
                vendor_user,
                "get_full_name",
            ):

                full_name = (
                    vendor_user.get_full_name()
                    or ""
                ).strip()

            vendor_name = (
                full_name
                or getattr(
                    vendor_user,
                    "email",
                    "",
                )
                or ""
            )

        if not vendor_name:
            vendor_name = str(vendor)

    # ========================================================
    # 9. MODES DE PAIEMENT
    # ========================================================

    modes = []

    for paiement in facture.paiements.all():

        for ligne in paiement.lignes.all():

            mode_obj = getattr(
                ligne,
                "mode_paiement",
                None,
            )

            if mode_obj is None:
                continue

            mode_nom = (
                getattr(
                    mode_obj,
                    "nom",
                    None,
                )
                or getattr(
                    mode_obj,
                    "code",
                    None,
                )
                or str(mode_obj)
            )

            if mode_nom and mode_nom not in modes:
                modes.append(mode_nom)

    payment_mode = ", ".join(modes)

    # ========================================================
    # 10. DATE DE FACTURE
    # ========================================================

    date_creation = getattr(
        facture,
        "date_creation",
        None,
    )

    if (
        date_creation is not None
        and timezone.is_aware(date_creation)
    ):

        date_creation = timezone.localtime(
            date_creation
        )

    date_txt = (
        date_creation.strftime(
            "%d/%m/%Y %H:%M"
        )
        if date_creation is not None
        else ""
    )

    # ========================================================
    # 11. QR CODE
    # ========================================================

    qr_code_path = None

    qr_field = getattr(
        facture,
        "qr_code_image",
        None,
    )

    if qr_field:

        try:
            qr_code_path = qr_field.path

        except (
            AttributeError,
            ValueError,
            NotImplementedError,
        ):
            qr_code_path = None

    # ========================================================
    # 12. DONNÉES FINALES
    # ========================================================

    return {

        # ----------------------------------------------------
        # Bijouterie
        # ----------------------------------------------------

        "shop_name": shop_name,
        "shop_phone": shop_phone,
        "shop_ninea": shop_ninea,
        "shop_address": shop_address,

        # ----------------------------------------------------
        # Facture
        # ----------------------------------------------------

        "title": (
            "FACTURE PROFORMA"
            if facture.type_facture == facture.TYPE_PROFORMA
            else "FACTURE"
        ),

        "invoice_no": facture.numero_facture,
        "invoice_type": facture.type_facture,
        "status": facture.status,
        "date": date_txt,
        "qr_code_path": qr_code_path,

        # ----------------------------------------------------
        # Client
        # ----------------------------------------------------

        "client_name": client_name,
        "client_phone": client_phone,
        "client_address": client_address,

        # ----------------------------------------------------
        # Vente / vendeur
        # ----------------------------------------------------

        "vendor": vendor_name,
        "cashier": "",
        "sale_no": vente.numero_vente,

        # ----------------------------------------------------
        # Paiement
        # ----------------------------------------------------

        "payment_mode": payment_mode,

        # ----------------------------------------------------
        # Lignes
        # ----------------------------------------------------

        "lines": lines,

        # ----------------------------------------------------
        # Totaux validés
        # ----------------------------------------------------

        "total_ht": total_ht,
        "appliquer_tva": appliquer_tva,
        "taux_tva": taux_tva,
        "montant_tva": montant_tva,
        "frais_transaction": frais_transaction,
        "total_ttc": total_ttc,
        "amount_paid": amount_paid,
        "remaining_amount": remaining_amount,
        "deposit_amount": ZERO,

        # ----------------------------------------------------
        # Pied de facture
        # ----------------------------------------------------

        "thanks": "Merci pour votre confiance.",

        "footer_note": (
            "Bijouterie Rio-Gold - L'excellence en or."
        ),
    }
    

