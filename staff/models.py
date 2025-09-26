from django.conf import settings
from django.db import models

class StaffProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="%(class)s_profile",   # évite les collisions futures
    )
    bijouterie = models.ForeignKey(
        "store.Bijouterie",                 # référence par chaîne = pas d’import direct
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="%(class)ss",          # donnera 'cashiers'
    )
    verifie = models.BooleanField(default=True)
    raison_desactivation = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def slug(self):
        return getattr(self.user, "slug", None)

    class Meta:
        abstract = True
        indexes = [models.Index(fields=["verifie"])]

class Cashier(StaffProfile):
    class Meta:
        verbose_name = "Caissier"
        verbose_name_plural = "Caissiers"
        ordering = ["-id"]

    def __str__(self):
        if self.user:
            return f"Caissier {getattr(self.user, 'username', self.user_id)}"
        return f"Caissier #{self.pk}"