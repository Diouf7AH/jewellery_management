# staff/models.py
from django.conf import settings
from django.db import models

class StaffCore(models.Model):
    """Mixin abstrait: ne contient AUCUNE FK dont on veut contrôler les reverse names."""
    verifie = models.BooleanField(default=True, db_index=True)
    raison_desactivation = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property 
    def slug(self): return getattr(self.user, "slug", None)
    
    class Meta:
        abstract = True


class Cashier(StaffCore):
    # Ici on fixe les reverse names EXACTS voulus pour Cashier
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="staff_cashier_profile",    # ✅ user.staff_cashier_profile
        related_query_name="cashier_profile",
    )
    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="cashiers",                 # ✅ bijouterie.cashiers.all()
        related_query_name="cashier",
    )

    class Meta:
        verbose_name = "Caissier"
        verbose_name_plural = "Caissiers"
        ordering = ["-id"]

    def __str__(self):
        return f"Caissier {getattr(self.user, 'username', self.user_id) if self.user else '#'+str(self.pk)}"


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

    class Meta:
        verbose_name = "Manager"
        verbose_name_plural = "Managers"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["verifie"]),
            models.Index(fields=["bijouterie"]),
        ]



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