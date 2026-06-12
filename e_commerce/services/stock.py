from django.core.exceptions import ValidationError
from django.db.models import F

from inventory.models import Bucket, InventoryMovement, MovementType
from stock.models import Stock


def decrease_bijouterie_stock(*, commande, vente, facture, vendor, lignes_map):
    for item in lignes_map:
        commande_ligne = item["commande_ligne"]
        vente_ligne = item["vente_ligne"]

        stock = Stock.objects.select_for_update().filter(
            produit_line=commande_ligne.produit_line,
            bijouterie=commande.bijouterie,
            is_reserve=False,
        ).first()

        if not stock:
            raise ValidationError(
                f"Aucun stock bijouterie pour {commande_ligne.produit}."
            )

        if stock.en_stock < commande_ligne.quantite:
            raise ValidationError(
                f"Stock insuffisant pour {commande_ligne.produit}."
            )

        Stock.objects.filter(pk=stock.pk).update(
            en_stock=F("en_stock") - commande_ligne.quantite
        )

        InventoryMovement.objects.create(
            produit=commande_ligne.produit,
            movement_type=MovementType.SALE_OUT,
            qty=commande_ligne.quantite,
            produit_line=commande_ligne.produit_line,
            vente=vente,
            vente_ligne=vente_ligne,
            facture=facture,
            src_bucket=Bucket.BIJOUTERIE,
            src_bijouterie=commande.bijouterie,
            dst_bucket=Bucket.EXTERNAL,
            vendor=vendor,
            stock_consumed=True,
            reason="Sortie stock e-commerce",
        )

