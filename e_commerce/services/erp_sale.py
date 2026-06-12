from e_commerce.services.vendor import get_or_create_ecommerce_vendor
from sale.models import (Facture, ModePaiement, Paiement, PaiementLigne, Vente,
                         VenteProduit)


def create_erp_sale_from_ecommerce(*, commande, paiement_ecommerce):
    vendor = get_or_create_ecommerce_vendor(
        bijouterie=commande.bijouterie
    )

    vente = Vente.objects.create(
        client=commande.client,
        bijouterie=commande.bijouterie,
        vendor=vendor,
        source_vente=Vente.SOURCE_ECOMMERCE,
        montant_total=commande.montant_total,
    )

    lignes_map = []

    for ligne in commande.lignes.select_related("produit", "produit_line").all():
        vente_ligne = VenteProduit.objects.create(
            vente=vente,
            produit=ligne.produit,
            vendor=vendor,
            quantite=ligne.quantite,
            prix_vente_grammes=ligne.prix_unitaire,
        )

        lignes_map.append({
            "commande_ligne": ligne,
            "vente_ligne": vente_ligne,
        })

    vente.mettre_a_jour_montant_total()

    facture = Facture.objects.create(
        vente=vente,
        bijouterie=commande.bijouterie,
        montant_ht=vente.montant_total,
        type_facture=Facture.TYPE_FACTURE,
        status=Facture.STAT_PAYE,
    )

    mode, _ = ModePaiement.objects.get_or_create(
        code=paiement_ecommerce.mode,
        defaults={
            "nom": paiement_ecommerce.get_mode_display(),
            "active": True,
            "necessite_reference": True,
        },
    )

    paiement = Paiement.objects.create(
        facture=facture,
    )

    PaiementLigne.objects.create(
        paiement=paiement,
        mode_paiement=mode,
        montant_paye=paiement_ecommerce.montant,
        reference=(
            paiement_ecommerce.provider_reference
            or paiement_ecommerce.transaction_id
            or paiement_ecommerce.reference_paiement
        ),
        provider_reference=paiement_ecommerce.provider_reference,
        checkout_url=paiement_ecommerce.checkout_url,
        payment_token=paiement_ecommerce.payment_token,
        callback_received=paiement_ecommerce.callback_received,
    )

    commande.vente = vente
    commande.facture = facture
    commande.save(update_fields=["vente", "facture", "updated_at"])

    return vente, facture, paiement, lignes_map

