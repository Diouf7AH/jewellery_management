# sale/services/facture_pdf_data_service.py

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.utils import timezone

from sale.models import Paiement, PaiementLigne, VenteAutre, VenteProduit

ZERO = Decimal("0.00")
TWOPLACES = Decimal("0.01")
HUNDRED = Decimal("100")


# ============================================================
# 1. VALIDATION FINANCIÈRE
# ============================================================

def validate_pdf_amount(
    value,
    field_name: str,
    *,
    allow_negative: bool = False,
) -> Decimal:
    """
    Valide un montant sans l'arrondir.

    Refuse :
        - None ;
        - chaînes vides ;
        - booléens ;
        - NaN et Infinity ;
        - valeurs négatives par défaut.

    Retourne un Decimal.
    """

    if value is None or (
        isinstance(value, str)
        and not value.strip()
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

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ) as exc:
        raise ValueError(
            f"La valeur '{field_name}' est invalide."
        ) from exc

    if not montant.is_finite():
        raise ValueError(
            f"La valeur '{field_name}' doit être finie."
        )

    if not allow_negative and montant < ZERO:
        raise ValueError(
            f"La valeur '{field_name}' "
            "ne peut pas être négative."
        )

    return montant


def validate_pdf_quantity(
    value,
    field_name: str,
) -> Decimal:
    """
    Vérifie une quantité strictement positive.
    """

    quantite = validate_pdf_amount(
        value,
        field_name,
    )

    if quantite <= ZERO:
        raise ValueError(
            f"La quantité '{field_name}' "
            "doit être strictement positive."
        )

    return quantite


def validate_pdf_percentage(
    value,
    field_name: str,
) -> Decimal:
    """
    Vérifie un pourcentage entre 0 et 100.
    """

    pourcentage = validate_pdf_amount(
        value,
        field_name,
    )

    if pourcentage > HUNDRED:
        raise ValueError(
            f"Le pourcentage '{field_name}' "
            "dépasse 100 %."
        )

    return pourcentage


def round_pdf_money(
    value: Decimal,
) -> Decimal:
    """
    Arrondit un montant à deux décimales.
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
# 2. HELPERS D'AFFICHAGE
# ============================================================

def _texte(value) -> str:
    """
    Convertit une valeur facultative en texte.
    """

    if value is None:
        return ""

    return str(value).strip()


def _date_locale(value):
    """
    Convertit une date Django dans le fuseau local.
    """

    if value is None:
        return None

    if timezone.is_aware(value):
        return timezone.localtime(value)

    return value


def _nom_client(client) -> str:
    """
    Retourne le nom du client.
    """

    if client is None:
        return ""

    prenom = _texte(
        getattr(client, "prenom", "")
    )

    nom = _texte(
        getattr(client, "nom", "")
    )

    return f"{prenom} {nom}".strip()


def _nom_vendeur(vendor) -> str:
    """
    Retourne le nom du vendeur.
    """

    if vendor is None:
        return ""

    vendor_user = getattr(
        vendor,
        "user",
        None,
    )

    if vendor_user is None:
        return _texte(vendor)

    full_name = ""

    if hasattr(vendor_user, "get_full_name"):
        full_name = _texte(
            vendor_user.get_full_name()
        )

    return (
        full_name
        or _texte(
            getattr(vendor_user, "email", "")
        )
        or _texte(vendor)
    )


def _chemin_qr(facture):
    """
    Retourne le chemin local du QR code
    lorsque le stockage le permet.

    Un stockage distant peut ne pas
    fournir de chemin local.
    """

    qr_field = getattr(
        facture,
        "qr_code_image",
        None,
    )

    if not qr_field:
        return None

    try:
        return qr_field.path

    except (
        AttributeError,
        ValueError,
        NotImplementedError,
        OSError,
    ):
        return None


# ============================================================
# 3. DONNÉES DES BIJOUX
# ============================================================

def _build_bijoux_lines(vente) -> list[dict]:
    """
    Prépare les lignes de bijoux.

    Ne recalcule pas les prix de vente :
    utilise les montants enregistrés.
    """

    lines = []

    lignes_bijoux = (
        VenteProduit.objects
        .filter(vente_id=vente.pk)
        .select_related(
            "produit_line__produit",
            "produit_line__produit__purete",
        )
        .order_by("pk")
    )

    for vp in lignes_bijoux:

        produit_line = vp.produit_line

        if produit_line is None:
            raise ValueError(
                f"Ligne bijou {vp.pk} : "
                "ProduitLine manquante."
            )

        produit = produit_line.produit

        if produit is None:
            raise ValueError(
                f"Ligne bijou {vp.pk} : "
                "produit manquant."
            )

        produit_nom = (
            getattr(produit, "nom", None)
            or "Produit non renseigné"
        )

        poids_valeur = getattr(
            produit,
            "poids",
            None,
        )

        poids = ""

        if poids_valeur is not None:
            poids = str(
                validate_pdf_amount(
                    poids_valeur,
                    f"bijou {vp.pk}.poids",
                )
            )

        purete_obj = getattr(
            produit,
            "purete",
            None,
        )

        purete = ""

        if purete_obj is not None:
            purete = _texte(
                getattr(
                    purete_obj,
                    "purete",
                    None,
                )
                or getattr(
                    purete_obj,
                    "nom",
                    None,
                )
                or purete_obj
            )

        if hasattr(
            produit_line,
            "get_etat_display",
        ):
            etat = _texte(
                produit_line.get_etat_display()
            )
        else:
            etat = _texte(
                getattr(
                    produit_line,
                    "etat",
                    "",
                )
            )

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

        pourcentage_occasion = (
            validate_pdf_percentage(
                vp.pourcentage_occasion,
                f"bijou {vp.pk}.pourcentage_occasion",
            )
            if vp.pourcentage_occasion is not None
            else ZERO
        )

        reduction_occasion = ZERO

        if getattr(
            produit_line,
            "etat",
            None,
        ) == "O":

            # Calcul sur le montant brut,
            # avant la réduction occasion.
            montant_brut = round_pdf_money(
                prix_gramme
                * validate_pdf_amount(
                    produit.poids,
                    f"bijou {vp.pk}.poids",
                )
                * quantite
            )

            reduction_occasion = round_pdf_money(
                montant_brut
                * pourcentage_occasion
                / HUNDRED
            )

        lines.append({
            "type_ligne": "bijou",
            "label": _texte(produit_nom),
            "poids": poids,
            "qty": quantite,
            "prix_gramme": prix_gramme,
            "prix_unitaire": ZERO,
            "total": montant_total_ligne,
            "purete": purete,
            "etat": etat,
            "pourcentage_occasion": (
                pourcentage_occasion
            ),
            "reduction_occasion": (
                reduction_occasion
            ),
        })

    return lines


# ============================================================
# 4. DONNÉES DES PRESTATIONS
# ============================================================

def _build_prestations_lines(
    vente,
) -> list[dict]:
    """
    Prépare les prestations d'une vente mixte.

    Les ventes contenant uniquement
    des prestations sont exclues
    par build_facture_pdf_data().
    """

    lines = []

    prestations = (
        VenteAutre.objects
        .filter(vente_id=vente.pk)
        .order_by("pk")
    )

    for autre in prestations:

        designation = _texte(
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

        montant_total = validate_pdf_amount(
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
            "total": montant_total,
            "purete": "",
            "etat": "",
            "pourcentage_occasion": ZERO,
            "reduction_occasion": ZERO,
        })

    return lines


# ============================================================
# 5. MODES DE PAIEMENT
# ============================================================

def _modes_paiement_facture(
    facture,
) -> str:
    """
    Retourne les modes de paiement utilisés
    pour cette facture, sans doublons.
    """

    modes = []
    modes_ids = set()

    lignes_paiement = (
        PaiementLigne.objects
        .filter(
            paiement__facture_id=facture.pk
        )
        .select_related("mode_paiement")
        .order_by("pk")
    )

    for ligne in lignes_paiement:

        mode = ligne.mode_paiement

        if mode is None:
            continue

        if mode.pk in modes_ids:
            continue

        modes_ids.add(mode.pk)

        nom = (
            getattr(mode, "nom", None)
            or getattr(mode, "code", None)
            or str(mode)
        )

        modes.append(_texte(nom))

    return ", ".join(modes)


# ============================================================
# 6. SERVICE PRINCIPAL
# ============================================================

def build_facture_pdf_data(
    facture,
) -> dict:
    """
    Prépare les données PDF d'une facture Rio-Gold.

    Ventes autorisées :
        - bijoux uniquement ;
        - bijoux + prestations.

    Ventes interdites :
        - prestations uniquement.

    Types autorisés :
        - proforma ;
        - facture définitive.

    Aucune modification de la base de données.
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

    if not VenteProduit.objects.filter(
        vente_id=vente.pk
    ).exists():
        raise ValueError(
            "Impossible de générer une facture "
            "pour une vente contenant uniquement "
            "des prestations."
        )

    if (
        facture.bijouterie_id
        != vente.bijouterie_id
    ):
        raise ValueError(
            "La facture et la vente appartiennent "
            "à des bijouteries différentes."
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

    client = getattr(
        vente,
        "client",
        None,
    )

    # ========================================================
    # 2. MONTANTS
    # ========================================================

    total_ht = validate_pdf_amount(
        facture.montant_ht,
        "facture.montant_ht",
    )

    frais_transaction = validate_pdf_amount(
        facture.frais_transaction,
        "facture.frais_transaction",
    )

    appliquer_tva = bool(
        facture.appliquer_tva
    )

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
            total_ht
            * taux_tva
            / HUNDRED
        )

        if montant_tva != tva_attendue:
            raise ValueError(
                "Incohérence financière : "
                "le montant TVA est incorrect."
            )

    else:

        taux_enregistre = validate_pdf_amount(
            (
                facture.taux_tva
                if facture.taux_tva is not None
                else ZERO
            ),
            "facture.taux_tva",
        )

        montant_enregistre = validate_pdf_amount(
            (
                facture.montant_tva
                if facture.montant_tva is not None
                else ZERO
            ),
            "facture.montant_tva",
        )

        if (
            taux_enregistre != ZERO
            or montant_enregistre != ZERO
        ):
            raise ValueError(
                "La TVA est désactivée mais "
                "un taux ou montant TVA non nul "
                "est enregistré."
            )

        taux_tva = ZERO
        montant_tva = ZERO

    total_ttc = validate_pdf_amount(
        facture.montant_total,
        "facture.montant_total",
    )

    total_attendu = round_pdf_money(
        total_ht
        + montant_tva
        + frais_transaction
    )

    if total_ttc != total_attendu:
        raise ValueError(
            "Incohérence financière : "
            "HT + TVA + frais de transaction "
            "ne correspond pas au TTC."
        )

    # ========================================================
    # 3. PAIEMENTS
    # ========================================================

    amount_paid = validate_pdf_amount(
        facture.total_paye,
        "facture.total_paye",
    )

    if amount_paid > total_ttc:
        raise ValueError(
            "Le total payé dépasse "
            "le montant de la facture."
        )

    remaining_amount = round_pdf_money(
        total_ttc - amount_paid
    )

    # ========================================================
    # 4. LIGNES DE VENTE
    # ========================================================

    bijoux_lines = _build_bijoux_lines(
        vente
    )

    prestations_lines = _build_prestations_lines(
        vente
    )

    lines = (
        bijoux_lines
        + prestations_lines
    )

    # ========================================================
    # 5. BIJOUTERIE
    # ========================================================

    shop_name = _texte(
        getattr(
            bijouterie,
            "nom",
            "",
        )
    ) or "RIO GOLD"

    shop_phone = _texte(
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
    )

    shop_ninea = _texte(
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
    )

    shop_address = _texte(
        getattr(
            bijouterie,
            "adresse",
            "",
        )
    )

    # ========================================================
    # 6. CLIENT
    # ========================================================

    client_name = _nom_client(
        client
    )

    client_phone = _texte(
        getattr(
            client,
            "telephone",
            "",
        )
    ) if client is not None else ""

    client_address = _texte(
        getattr(
            client,
            "adresse",
            "",
        )
    ) if client is not None else ""

    # ========================================================
    # 7. VENDEUR
    # ========================================================

    vendor_name = _nom_vendeur(
        getattr(
            vente,
            "vendor",
            None,
        )
    )

    # ========================================================
    # 8. PAIEMENTS
    # ========================================================

    payment_mode = _modes_paiement_facture(
        facture
    )

    # ========================================================
    # 9. DATE
    # ========================================================

    date_creation = _date_locale(
        facture.date_creation
    )

    date_txt = (
        date_creation.strftime(
            "%d/%m/%Y %H:%M"
        )
        if date_creation is not None
        else ""
    )

    # ========================================================
    # 10. QR CODE
    # ========================================================

    qr_code_path = _chemin_qr(
        facture
    )

    # ========================================================
    # 11. RÉSULTAT
    # ========================================================

    return {
        "shop_name": shop_name,
        "shop_phone": shop_phone,
        "shop_ninea": shop_ninea,
        "shop_address": shop_address,

        "title": (
            "FACTURE PROFORMA"
            if facture.type_facture
            == facture.TYPE_PROFORMA
            else "FACTURE"
        ),

        "invoice_no": facture.numero_facture,
        "invoice_type": facture.type_facture,
        "status": facture.status,
        "date": date_txt,
        "qr_code_path": qr_code_path,

        "client_name": client_name,
        "client_phone": client_phone,
        "client_address": client_address,

        "vendor": vendor_name,
        "cashier": "",
        "sale_no": vente.numero_vente,

        "payment_mode": payment_mode,
        "lines": lines,

        "total_ht": total_ht,
        "appliquer_tva": appliquer_tva,
        "taux_tva": taux_tva,
        "montant_tva": montant_tva,
        "frais_transaction": frais_transaction,
        "total_ttc": total_ttc,
        "amount_paid": amount_paid,
        "remaining_amount": remaining_amount,
        "deposit_amount": ZERO,

        "thanks": "Merci pour votre confiance.",
        "footer_note": (
            "Bijouterie Rio-Gold - "
            "L'excellence en or."
        ),
    }


