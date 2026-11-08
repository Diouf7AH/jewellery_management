from django.core.exceptions import ValidationError
from django.db.models import ExpressionWrapper, F, IntegerField

from sale.services.sale_context_service import \
    resolve_vendor_and_bijouterie_for_sale
from stock.models import VendorStock
from vendor.services.qr_utils import decode_etiquette_qr


def rechercher_lots_par_sku(
    *,
    user,
    role,
    sku=None,
    qr=None,
    vendor_email=None,
):
    """
    Recherche les lignes de lots disponibles.

    SKU :
        Recherche manuelle.
        Retourne les lots disponibles.

    QR :
        Recherche automatique.
        Retourne la ligne correspondant au QR.

    Aucun stock n'est modifié.
    """

    # =====================================================
    # 1. VALIDATION
    # =====================================================

    sku = str(sku or "").strip()
    qr = str(qr or "").strip()

    if not sku and not qr:
        raise ValidationError({
            "recherche": "Le SKU ou le QR code est obligatoire."
        })

    if sku and qr:
        raise ValidationError({
            "recherche": (
                "Fournissez soit le SKU, soit le QR code, "
                "mais pas les deux."
            )
        })

    # =====================================================
    # 2. VENDEUR ET BIJOUTERIE AUTORISÉS
    # =====================================================

    vendor, bijouterie = resolve_vendor_and_bijouterie_for_sale(
        user=user,
        role=role,
        vendor_email=vendor_email,
    )

    # =====================================================
    # 3. STOCK DISPONIBLE DU VENDEUR
    # =====================================================

    stocks = (
        VendorStock.objects
        .filter(
            vendor=vendor,
            bijouterie=bijouterie,
            produit_line__lot__achat__bijouterie=bijouterie,
        )
        .annotate(
            quantite_disponible=ExpressionWrapper(
                F("quantite_allouee") - F("quantite_vendue"),
                output_field=IntegerField(),
            )
        )
        .filter(
            quantite_disponible__gt=0
        )
    )

    # =====================================================
    # 4. RECHERCHE SKU OU QR
    # =====================================================

    if sku:
        stocks = stocks.filter(
            produit_line__produit__sku__iexact=sku
        )
        type_recherche = "sku"

    else:
        try:
            line_uuid = decode_etiquette_qr(qr)
        except ValueError as exc:
            raise ValidationError({
                "qr": str(exc)
            }) from exc

        stocks = stocks.filter(
            produit_line__uuid=line_uuid
        )
        type_recherche = "qr"

    # =====================================================
    # 5. CHARGEMENT DES LIGNES
    # =====================================================

    stocks = (
        stocks
        .select_related(
            "produit_line",
            "produit_line__produit",
            "produit_line__lot",
        )
        .order_by(
            "produit_line__lot__numero_lot",
            "produit_line__numero_ligne_lot",
            "produit_line_id",
        )
    )

    lignes = list(stocks)

    if not lignes:
        raise ValidationError({
            "recherche": (
                "Aucune ligne de lot disponible "
                "dans le stock du vendeur."
            )
        })

    # =====================================================
    # 6. RÉPONSE ANGULAR
    # =====================================================

    premiere_ligne = lignes[0].produit_line

    lots = []

    for stock in lignes:
        line = stock.produit_line

        lots.append({
            "produit_line_id": line.id,
            "uuid": str(line.uuid),
            "numero_lot": line.lot.numero_lot,
            "numero_ligne_lot": line.numero_ligne_lot,
            "etat": line.etat,
            "poids_unitaire_achat": (
                str(line.poids_unitaire_achat)
                if line.poids_unitaire_achat is not None
                else None
            ),
            "pourcentage_occasion": str(
                line.pourcentage_occasion
            ),
            "quantite_disponible": stock.quantite_disponible,
        })

    return {
        "type_recherche": type_recherche,
        "sku": premiere_ligne.produit.sku,
        "produit": {
            "id": premiere_ligne.produit_id,
        },
        "lots": lots,
    }
    

