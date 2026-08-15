# staff/models.py

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class StaffCore(models.Model):
    """
    Classe abstraite commune aux profils staff.

    La désactivation concerne uniquement le profil staff.
    Le compte utilisateur reste actif.
    """

    verifie = models.BooleanField(
        default=True,
        db_index=True,
    )

    raison_desactivation = models.TextField(
        null=True,
        blank=True,
    )

    date_desactivation = models.DateTimeField(
        null=True,
        blank=True,
    )

    desactive_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_desactives",
        related_query_name="%(app_label)s_%(class)s_desactive",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        abstract = True

    @property
    def full_name(self) -> str:
        user = getattr(self, "user", None)

        if not user:
            return f"Staff #{self.pk}"

        return (
            user.get_full_name()
            or getattr(user, "email", None)
            or f"Staff #{self.pk}"
        )

    @property
    def telephone(self):
        user = getattr(self, "user", None)

        if not user:
            return None

        return getattr(user, "telephone", None)

    @property
    def email(self):
        user = getattr(self, "user", None)

        if not user:
            return None

        return getattr(user, "email", None)

    @property
    def is_active_staff(self) -> bool:
        user = getattr(self, "user", None)

        return bool(
            self.verifie
            and user
            and getattr(user, "is_active", False)
        )

    def desactiver(
        self,
        *,
        by_user=None,
        raison: str = "",
    ):
        """
        Désactive uniquement le rôle staff.
        """

        raison = str(raison or "").strip()

        self.verifie = False
        self.raison_desactivation = (
            raison or "Staff désactivé."
        )
        self.date_desactivation = timezone.now()
        self.desactive_par = by_user

        self.save(
            update_fields=[
                "verifie",
                "raison_desactivation",
                "date_desactivation",
                "desactive_par",
                "updated_at",
            ]
        )

    def reactiver(self):
        """
        Réactive uniquement le rôle staff.
        """

        self.verifie = True
        self.raison_desactivation = None
        self.date_desactivation = None
        self.desactive_par = None

        self.save(
            update_fields=[
                "verifie",
                "raison_desactivation",
                "date_desactivation",
                "desactive_par",
                "updated_at",
            ]
        )


class Cashier(StaffCore):
    """
    Caissier rattaché à une seule bijouterie.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="staff_cashier_profile",
        related_query_name="cashier_profile",
    )

    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cashiers",
        related_query_name="cashier",
    )

    class Meta:
        verbose_name = "Caissier"
        verbose_name_plural = "Caissiers"
        ordering = ["-id"]

        indexes = [
            models.Index(
                fields=["bijouterie", "verifie"],
                name="idx_cashier_bij_verif",
            ),
        ]

    def __str__(self):
        return self.full_name


class Manager(StaffCore):
    """
    Manager pouvant gérer plusieurs bijouteries.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
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

    def __str__(self):
        return self.full_name


class Buyer(StaffCore):
    """
    Responsable des rachats clients ou matières premières.

    Il est rattaché à une seule bijouterie.

    Il n'intervient pas dans le cycle de stock produit :
        PURCHASE_IN
        VENDOR_ASSIGN
        SALE_OUT
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="staff_buyer_profile",
        related_query_name="buyer_profile",
    )

    bijouterie = models.ForeignKey(
        "store.Bijouterie",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="buyers",
        related_query_name="buyer",
    )

    class Meta:
        verbose_name = "Responsable rachat"
        verbose_name_plural = "Responsables rachats"
        ordering = ["-id"]

        indexes = [
            models.Index(
                fields=["bijouterie", "verifie"],
                name="idx_buyer_bij_verif",
            ),
        ]

    def __str__(self):
        return self.full_name
    
    
