from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from e_commerce.models import (CommandeEcommerce, LivraisonEcommerce,
                               PaiementEcommerce)
from e_commerce.services.email import send_ecommerce_order_paid_email
from e_commerce.services.erp_sale import create_erp_sale_from_ecommerce
from e_commerce.services.payment import mark_payment_success
from e_commerce.services.stock import decrease_bijouterie_stock


@transaction.atomic
def confirm_ecommerce_payment(
    *,
    paiement,
    payload=None,
):
    payload = payload or {}

    # ============================================================
    # 1. VÉRIFIER LE STATUT RETOURNÉ PAR LE PROVIDER
    # ============================================================

    provider_status = str(
        payload.get("status", "")
    ).strip().lower()

    if provider_status not in {
        "success",
        "paid",
        "completed",
    }:
        raise ValidationError(
            "Le paiement n'a pas été confirmé "
            "par le fournisseur."
        )

    # ============================================================
    # 2. VERROUILLER PAIEMENT E-COMMERCE
    # ============================================================

    paiement = (
        PaiementEcommerce.objects
        .select_for_update()
        .select_related(
            "commande",
            "commande__bijouterie",
        )
        .get(
            pk=paiement.pk
        )
    )

    # ============================================================
    # 3. VERROUILLER COMMANDE
    # ============================================================

    commande = (
        CommandeEcommerce.objects
        .select_for_update()
        .select_related(
            "bijouterie",
            "client",
        )
        .get(
            pk=paiement.commande_id
        )
    )

    # ============================================================
    # 4. IDEMPOTENCE
    #
    # Si le provider renvoie plusieurs fois le même webhook,
    # ne jamais recréer Vente / Facture / sortie stock.
    # ============================================================

    if (
        commande.status
        == CommandeEcommerce.STATUS_PAID
    ):
        return commande

    if (
        paiement.status
        == PaiementEcommerce.STATUS_SUCCESS
    ):
        return commande

    # ============================================================
    # 5. VÉRIFIER LE MONTANT PROVIDER
    # ============================================================

    montant_provider_raw = (
        payload.get("montant")
        or payload.get("amount")
    )

    if montant_provider_raw is None:
        raise ValidationError(
            "Le montant confirmé par le fournisseur "
            "est manquant."
        )

    try:
        montant_provider = Decimal(
            str(montant_provider_raw)
        ).quantize(
            Decimal("0.01")
        )

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        raise ValidationError(
            "Le montant confirmé par le fournisseur "
            "est invalide."
        )

    montant_paiement = Decimal(
        str(paiement.montant)
    ).quantize(
        Decimal("0.01")
    )

    montant_commande = Decimal(
        str(commande.montant_a_payer)
    ).quantize(
        Decimal("0.01")
    )

    # Provider = PaiementEcommerce
    if montant_provider != montant_paiement:
        raise ValidationError(
            "Le montant confirmé par le fournisseur "
            "ne correspond pas au montant attendu."
        )

    # PaiementEcommerce = CommandeEcommerce
    if montant_paiement != montant_commande:
        raise ValidationError(
            "Le montant du paiement ne correspond pas "
            "au montant de la commande."
        )

    # ============================================================
    # 6. VÉRIFIER LA COMMANDE
    # ============================================================

    if (
        commande.status
        != CommandeEcommerce.STATUS_PENDING
    ):
        raise ValidationError(
            "La commande n'est pas dans un état "
            "permettant la confirmation du paiement."
        )

    # ============================================================
    # 7. CRÉER VENTE + FACTURE + PAIEMENT ERP
    #
    # Si le stock devient insuffisant ensuite,
    # transaction.atomic() annulera tout.
    # ============================================================

    (
        vente,
        facture,
        paiement_erp,
        lignes_map,
    ) = create_erp_sale_from_ecommerce(
        commande=commande,
        paiement_ecommerce=paiement,
    )

    # ============================================================
    # 8. DEUXIÈME VÉRIFICATION + CONSOMMATION DU STOCK
    #
    # decrease_bijouterie_stock() doit :
    # - select_for_update() Stock ;
    # - vérifier Stock.en_stock ;
    # - diminuer uniquement en_stock ;
    # - créer InventoryMovement SALE_OUT.
    # ============================================================

    decrease_bijouterie_stock(
        commande=commande,
        vente=vente,
        facture=facture,
        lignes_map=lignes_map,
    )

    # ============================================================
    # 9. MARQUER LE PAIEMENT E-COMMERCE SUCCESS
    # ============================================================

    mark_payment_success(
        paiement=paiement,
        payload=payload,
    )

    # ============================================================
    # 10. MARQUER LA COMMANDE PAYÉE
    # ============================================================

    commande.status = (
        CommandeEcommerce.STATUS_PAID
    )

    commande.paid_at = timezone.now()

    commande.save(
        update_fields=[
            "status",
            "paid_at",
            "updated_at",
        ]
    )

    # ============================================================
    # 11. CRÉER LA LIVRAISON
    # ============================================================

    LivraisonEcommerce.objects.get_or_create(
        commande=commande,
        defaults={
            "adresse_livraison": (
                commande.adresse_livraison
                or ""
            ),
            "telephone_client": (
                commande.telephone_client
            ),
            "status": (
                LivraisonEcommerce
                .STATUS_PREPARATION
            ),
        },
    )

    # ============================================================
    # 12. EMAIL APRÈS COMMIT
    # ============================================================

    transaction.on_commit(
        lambda: send_ecommerce_order_paid_email(
            commande=commande
        )
    )

    return commande


