# administration/models.py

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from backend.roles import ROLE_ADMIN, get_role_name
from staff.models import StaffCore


class AdminProfile(StaffCore):

    class Niveau(models.TextChoices):
        PRINCIPAL = "principal", "Principal"
        SECONDAIRE = "secondaire", "Secondaire"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="admin_profile",
    )

    niveau = models.CharField(
        max_length=20,
        choices=Niveau.choices,
        default=Niveau.SECONDAIRE,
        db_index=True,
    )

    # MySQL : une seule valeur 1 autorisée.
    # Plusieurs valeurs NULL sont autorisées.
    principal_unique_key = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        unique=True,
        editable=False,
    )

    peut_gerer_bijouteries = models.BooleanField(
        default=False,
    )

    peut_voir_finances = models.BooleanField(
        default=False,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="admin_profiles_created",
    )

    class Meta:
        verbose_name = "Administrateur"
        verbose_name_plural = "Administrateurs"

    def clean(self):
        super().clean()

        # Synchronisation de la clé unique.
        self.principal_unique_key = (
            1
            if self.niveau == self.Niveau.PRINCIPAL
            else None
        )

        if self.user_id:

            if get_role_name(self.user) != ROLE_ADMIN:
                raise ValidationError({
                    "user": (
                        "L'utilisateur doit posséder "
                        "le rôle administrateur."
                    )
                })

        if (
            self.niveau == self.Niveau.PRINCIPAL
            and not self.verifie
        ):
            raise ValidationError({
                "verifie": (
                    "L'administrateur principal "
                    "ne peut pas être désactivé."
                )
            })

    def save(self, *args, **kwargs):

        self.principal_unique_key = (
            1
            if self.niveau == self.Niveau.PRINCIPAL
            else None
        )

        update_fields = kwargs.get("update_fields")

        if update_fields is not None:
            update_fields = set(update_fields)
            update_fields.add("principal_unique_key")
            kwargs["update_fields"] = update_fields

        super().save(*args, **kwargs)

    @property
    def est_principal(self):
        return bool(
            self.verifie
            and self.user.is_active
            and self.niveau == self.Niveau.PRINCIPAL
            and get_role_name(self.user) == ROLE_ADMIN
        )

    @property
    def est_secondaire(self):
        return bool(
            self.verifie
            and self.user.is_active
            and self.niveau == self.Niveau.SECONDAIRE
            and get_role_name(self.user) == ROLE_ADMIN
        )

    def __str__(self):
        return (
            f"{self.user} - "
            f"{self.get_niveau_display()}"
        )
