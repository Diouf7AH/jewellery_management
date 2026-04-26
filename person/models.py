import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.html import mark_safe

from store.models import Bijouterie


class Sex(models.TextChoices):
    M = "M", "Homme"
    F = "F", "Femme"


class PersonBase(models.Model):
    nom = models.CharField(max_length=100, null=True, blank=True)
    prenom = models.CharField(max_length=100, null=True, blank=True)
    telephone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    image = models.ImageField(upload_to="user-images/", null=True, blank=True)
    sexe = models.CharField(max_length=1, choices=Sex.choices, null=True, blank=True)
    date_naissance = models.DateField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    active = models.BooleanField(default=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    @property
    def full_name(self):
        return " ".join(filter(None, [self.prenom, self.nom])).strip()

    def clean(self):
        super().clean()

        if self.telephone:
            t = self.telephone.strip().replace(" ", "")
            if t.startswith("+"):
                t = t[1:]

            if not re.fullmatch(r"\d{9,15}", t):
                raise ValidationError({
                    "telephone": "Le numéro doit contenir 9 à 15 chiffres."
                })

            self.telephone = t

    def person_image(self):
        if self.image and hasattr(self.image, "url"):
            return mark_safe(
                f'<img src="{self.image.url}" width="50" height="50" '
                'style="object-fit:cover;border-radius:6px;" />'
            )
        return "—"

    person_image.short_description = "Photo"

    def __str__(self):
        return self.full_name or f"Personne #{self.pk}"


class Employee(PersonBase):
    bijouterie = models.ForeignKey(
        Bijouterie,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )

    class Meta:
        verbose_name = "Employé"
        verbose_name_plural = "Employés"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["active"]),
            models.Index(fields=["nom", "prenom"]),
        ]

    def __str__(self):
        return self.full_name or f"Employé #{self.pk}"


class Ouvrier(PersonBase):
    bijouterie = models.ForeignKey(
        Bijouterie,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ouvriers",
    )
    specialite = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        verbose_name = "Ouvrier"
        verbose_name_plural = "Ouvriers"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["active"]),
            models.Index(fields=["nom", "prenom"]),
        ]

    def __str__(self):
        return self.full_name or f"Ouvrier #{self.pk}"


# class Client(PersonBase):
#     user = models.OneToOneField(
#         settings.AUTH_USER_MODEL,
#         on_delete=models.SET_NULL,
#         null=True,
#         blank=True,
#         related_name="client_profile",
#     )

#     class Meta:
#         verbose_name = "Client"
#         verbose_name_plural = "Clients"
#         ordering = ["-id"]
#         indexes = [
#             models.Index(fields=["active"]),
#             models.Index(fields=["nom", "prenom"]),
#         ]

#     def __str__(self):
#         return self.full_name or f"Client #{self.pk}"
    
    
