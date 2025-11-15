# staff/models.py
from django.conf import settings
from django.db import models

from store.models import Bijouterie


class StaffCore(models.Model):
    verifie = models.BooleanField(default=True, db_index=True)
    raison_desactivation = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        indexes = [models.Index(fields=["verifie"])]

class Cashier(StaffCore):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="staff_cashier_profile",
        related_query_name="cashier_profile",
    )
    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="cashiers",
        related_query_name="cashier",
    )

class Manager(StaffCore):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="staff_manager_profile",
        related_query_name="manager_profile",
    )
    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="managers",
        related_query_name="manager",
    )

# # Exemple d’une autre sous-classe (si tu en as d’autres)
# class Manager(StaffCore):
#     user = models.OneToOneField(
#         settings.AUTH_USER_MODEL,
#         on_delete=models.SET_NULL,
#         null=True,
#         related_name="staff_manager_profile",    # ✅ user.staff_manager_profile
#         related_query_name="manager_profile",
#     )
#     bijouterie = models.ForeignKey(
#         "store.Bijouterie",
#         on_delete=models.SET_NULL,
#         null=True, blank=True,
#         related_name="managers",                 # ✅ bijouterie.managers.all()
#         related_query_name="manager",
#     )

#     class Meta:
#         verbose_name = "Manager"
#         verbose_name_plural = "Managers"
#         ordering = ["-id"]