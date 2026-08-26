from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from inventory.models import Bucket, MovementType
from inventory.services import log_move
from stock.models import Stock


@transaction.atomic
def decrease_bijouterie_stock(
    *,
    commande,
    vente,
    facture,
    lignes_map,
):
    for item in lignes_map:
        commande_ligne = item["commande_ligne"]
        vente_ligne = item["vente_ligne"]

        stock = (
            Stock.objects
            .select_for_update()
            .filter(
                produit_line=commande_ligne.produit_line,
                bijouterie=commande.bijouterie,
            )
            .first()
        )

        if stock is None:
            raise ValidationError(
                f"Aucun stock dans la bijouterie "
                f"pour {commande_ligne.produit}."
            )

        quantite = int(commande_ligne.quantite)

        if quantite <= 0:
            raise ValidationError(
                "La quantité à sortir doit être "
                "supérieure à zéro."
            )

        if stock.en_stock < quantite:
            raise ValidationError(
                f"Stock insuffisant pour "
                f"{commande_ligne.produit}. "
                f"Disponible : {stock.en_stock}, "
                f"demandé : {quantite}."
            )

        updated = (
            Stock.objects
            .filter(
                pk=stock.pk,
                en_stock__gte=quantite,
            )
            .update(
                en_stock=F("en_stock") - quantite
            )
        )

        if updated != 1:
            raise ValidationError(
                f"Stock insuffisant pour "
                f"{commande_ligne.produit}."
            )

        log_move(
            produit=commande_ligne.produit,
            qty=quantite,
            movement_type=MovementType.SALE_OUT,
            src_bucket=Bucket.BIJOUTERIE,
            dst_bucket=Bucket.EXTERNAL,
            src_bijouterie_id=commande.bijouterie_id,
            produit_line=commande_ligne.produit_line,
            vente=vente,
            vente_ligne=vente_ligne,
            facture=facture,
            stock_consumed=True,
            reason="Sortie stock e-commerce",
        )
        
    