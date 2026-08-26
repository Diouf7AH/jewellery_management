from django.core.exceptions import ValidationError

from sale.models import (Facture, ModePaiement, Paiement, PaiementLigne, Vente,
                         VenteProduit)


def create_erp_sale_from_ecommerce(
    *,
    commande,
    paiement_ecommerce,
):
    # ============================================================
    # 1. RÉFÉRENCE PAIEMENT
    # ============================================================

    reference_paiement = (
        paiement_ecommerce.provider_reference
        or paiement_ecommerce.transaction_id
        or paiement_ecommerce.reference_paiement
    )

    if not reference_paiement:
        raise ValidationError(
            "Aucune référence de paiement n'est disponible "
            "pour créer le paiement ERP."
        )

    # ============================================================
    # 2. CRÉER LA VENTE ERP
    #
    # Vente e-commerce :
    # - pas de vendeur physique ;
    # - consommation directe Stock bijouterie.
    # ============================================================

    vente = Vente.objects.create(
        client=commande.client,
        bijouterie=commande.bijouterie,
        vendor=None,
        source_vente=Vente.SOURCE_ECOMMERCE,
    )

    # ============================================================
    # 3. CRÉER LES LIGNES DE VENTE
    # ============================================================

    lignes_map = []

    lignes_commande = (
        commande.lignes
        .select_related(
            "produit",
            "produit_line",
        )
        .all()
    )

    for ligne in lignes_commande:
        vente_ligne = VenteProduit.objects.create(
            vente=vente,
            produit=ligne.produit,
            vendor=None,
            quantite=ligne.quantite,
            prix_vente_grammes=ligne.prix_gramme,
        )

        lignes_map.append({
            "commande_ligne": ligne,
            "vente_ligne": vente_ligne,
        })

    # ============================================================
    # 4. RECALCULER LA VENTE
    # ============================================================

    vente.mettre_a_jour_montant_total()

    # ============================================================
    # 5. CRÉER LA FACTURE
    #
    # Les valeurs TVA sont figées depuis la commande.
    # ============================================================

    facture = Facture.objects.create(
        vente=vente,
        bijouterie=commande.bijouterie,

        montant_ht=commande.montant_total,

        appliquer_tva=commande.appliquer_tva,

        taux_tva=(
            commande.taux_tva
            if commande.appliquer_tva
            else None
        ),

        frais_transaction=commande.frais_transaction,

        type_facture=Facture.TYPE_FACTURE,
        status=Facture.STAT_PAYE,
    )

    # ============================================================
    # 6. MODE DE PAIEMENT ERP
    # ============================================================

    mode, _ = ModePaiement.objects.get_or_create(
        code=paiement_ecommerce.mode,
        defaults={
            "nom": (
                paiement_ecommerce
                .get_mode_display()
            ),
            "active": True,
            "necessite_reference": True,
        },
    )

    # ============================================================
    # 7. PAIEMENT ERP
    # ============================================================

    paiement = Paiement.objects.create(
        facture=facture,
    )

    PaiementLigne.objects.create(
        paiement=paiement,
        mode_paiement=mode,
        montant_paye=paiement_ecommerce.montant,

        reference=reference_paiement,

        provider_reference=(
            paiement_ecommerce.provider_reference
        ),

        checkout_url=(
            paiement_ecommerce.checkout_url
        ),

        payment_token=(
            paiement_ecommerce.payment_token
        ),

        # Nous sommes ici uniquement après
        # confirmation réelle du provider.
        callback_received=True,
    )

    # ============================================================
    # 8. RATTACHER VENTE + FACTURE À LA COMMANDE
    # ============================================================

    commande.vente = vente
    commande.facture = facture

    commande.save(
        update_fields=[
            "vente",
            "facture",
            "updated_at",
        ]
    )

    return (
        vente,
        facture,
        paiement,
        lignes_map,
    )
    

