from __future__ import annotations

from django.utils import timezone

from inventory.models import Bucket, InventoryMovement, MovementType
from sale.models import Facture, Vente, VenteProduit


def create_sale_out(*, facture: Facture, vente: Vente, ligne: VenteProduit, by_user) -> bool:
    """
    Audit SALE_OUT par ligne.
    Idempotence: ta contrainte UniqueConstraint(sale_out_key=vente_ligne_id)
    va empêcher les doublons.
    Retour True si créé, False si déjà existait.
    """
    try:
        InventoryMovement.objects.create(
            produit=ligne.produit,
            movement_type=MovementType.SALE_OUT,
            qty=ligne.quantite,
            unit_cost=None,
            lot=None,
            reason=f"Vente {vente.numero_vente} / Facture {facture.numero_facture} / ligne {ligne.id}",
            src_bucket=Bucket.BIJOUTERIE,
            src_bijouterie=facture.bijouterie,
            dst_bucket=Bucket.EXTERNAL,
            dst_bijouterie=None,
            facture=facture,
            vente=vente,
            vente_ligne=ligne,
            occurred_at=timezone.now(),
            created_by=by_user,
            vendor=ligne.vendor,
        )
        return True
    except Exception as e:
        msg = str(e).lower()
        if "sale_out" in msg or "sale out key" in msg or "uniq_sale_out" in msg:
            return False
        raise


def create_return_in(*, facture: Facture, vente: Vente, ligne: VenteProduit, by_user) -> None:
    """
    Audit RETURN_IN (annulation): EXTERNAL -> BIJOUTERIE
    """
    InventoryMovement.objects.create(
        produit=ligne.produit,
        movement_type=MovementType.RETURN_IN,
        qty=ligne.quantite,
        unit_cost=None,
        lot=None,
        reason=f"Annulation vente {vente.numero_vente} / Facture {facture.numero_facture} / ligne {ligne.id}",
        src_bucket=Bucket.EXTERNAL,
        src_bijouterie=None,
        dst_bucket=Bucket.BIJOUTERIE,
        dst_bijouterie=facture.bijouterie,
        facture=facture,
        vente=vente,
        vente_ligne=ligne,
        occurred_at=timezone.now(),
        created_by=by_user,
        vendor=ligne.vendor,
    )

