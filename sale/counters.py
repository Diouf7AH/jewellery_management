# Compteur par bijouterie et par jour
from django.db import models, transaction
from django.db.models import F
from django.utils import timezone
from store.models import Bijouterie

# pour les numero de facture
class InvoiceCounter(models.Model):
    bijouterie = models.ForeignKey(Bijouterie, on_delete=models.CASCADE, related_name="invoice_counters")
    day = models.DateField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["bijouterie", "day"], name="uniq_invoice_counter_per_shop_day"),
        ]
        indexes = [models.Index(fields=["bijouterie", "day"])]

    @classmethod
    def next_for_today(cls, bijouterie) -> int:
        if not bijouterie:
            raise ValueError("Bijouterie requise pour incrémenter le compteur.")
        today = timezone.localdate()
        with transaction.atomic():
            row, _ = (cls.objects
                        .select_for_update()
                        .get_or_create(bijouterie=bijouterie, day=today, defaults={"last_value": 0}))
            row.last_value = F("last_value") + 1
            row.save(update_fields=["last_value"])
            row.refresh_from_db(fields=["last_value"])
            return row.last_value