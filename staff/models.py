from django.conf import settings
from django.db import models


class StaffCore(models.Model):
    verifie = models.BooleanField(default=True, db_index=True)
    raison_desactivation = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        indexes = [models.Index(fields=["verifie"])]

    @property
    def full_name(self):
        if not getattr(self, "user", None):
            return f"Staff #{self.pk}"
        return self.user.get_full_name() or self.user.email

    @property
    def telephone(self):
        if not getattr(self, "user", None):
            return None
        return getattr(self.user, "telephone", None)

    @property
    def email(self):
        if not getattr(self, "user", None):
            return None
        return getattr(self.user, "email", None)

    @property
    def is_active_staff(self):
        """
        Actif au sens métier + compte actif.
        """
        user = getattr(self, "user", None)
        return bool(self.verifie and user and user.is_active)


class Cashier(StaffCore):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_cashier_profile",
        related_query_name="cashier_profile",
    )
    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cashiers",
        related_query_name="cashier",
    )

    class Meta:
        verbose_name = "Caissier"
        verbose_name_plural = "Caissiers"
        ordering = ["-id"]

    def __str__(self):
        return self.full_name or f"Caissier #{self.pk}"


# class Manager(StaffCore):
#     user = models.OneToOneField(
#         settings.AUTH_USER_MODEL,
#         on_delete=models.CASCADE,
#         related_name="staff_manager_profile",
#         related_query_name="manager_profile",
#     )
#     bijouteries = models.ManyToManyField(
#         "store.Bijouterie",
#         blank=True,
#         related_name="managers",
#         related_query_name="manager",
#     )

#     class Meta:
#         verbose_name = "Manager"
#         verbose_name_plural = "Managers"
#         ordering = ["-id"]

#     def __str__(self):
#         return self.full_name or f"Manager #{self.pk}"


class Manager(StaffCore):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="staff_manager_profile",
        related_query_name="manager_profile",
    )
    bijouteries = models.ManyToManyField(
        "store.Bijouterie",
        blank=True,
        related_name="managers",
        related_query_name="manager",
    )

    class Meta:
        verbose_name = "Manager"
        verbose_name_plural = "Managers"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["verifie"]),
        ]

    def __str__(self):
        if self.user:
            return f"Manager {self.user.email or self.user.id}"
        return self.full_name or f"Manager #{self.pk}"
    
    
    
    
    

