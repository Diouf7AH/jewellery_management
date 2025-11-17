from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Sum
from .models import Paiement
from .models import Facture  # adapte import si modèles séparés

# mettre à jour le statut de la facture automatiquement
@receiver(post_save, sender=Paiement)
def update_facture_status(sender, instance, created, **kwargs):
    if not created:
        return
    f = instance.facture
    total = getattr(f, "montant_total", None)
    if total is None:
        return
    total_paye = f.paiements.aggregate(t=Sum("montant_paye"))["t"] or Decimal("0.00")
    if total_paye >= total and getattr(Facture, "STAT_PAYE", None):
        f.status = Facture.STAT_PAYE
        f.save(update_fields=["status"])


