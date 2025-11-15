from django.db import models
from django.utils import timezone
from django.utils.html import mark_safe

from store.models import Bijouterie

# from userauths.models import user_directory_path


# Create your models here.
# class Employee(models.Model):
#     name = models.CharField(max_length=100, help_text="Shop Name", null=True, blank=True)
#     phone =  models.CharField(max_length=20,unique=True,null=True)
#     image = models.ImageField(upload_to='user-images/', blank=True)
#     # image = models.ImageField(upload_to=user_directory_path, default="shop-image.jpg", blank=True)
#     bijoterie = models.ForeignKey(Bijouterie, on_delete=models.SET_NULL, null=True, blank=True, related_name="vendor_bijoutrie")
#     description = models.TextField(null=True, blank=True)
#     active = models.BooleanField(default=True)
#     date = models.DateTimeField(auto_now_add=True)
    
#     class Meta:
#         verbose_name_plural = "Employees"

#     def employee_image(self):
#         return mark_safe('  <img src="%s" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />' % (self.shop_image.url))

#     def __str__(self):
#         return str(self.name)

class Employee(models.Model):
    name = models.CharField(max_length=100, help_text="Nom et prénom de l’employé", null=True, blank=True)
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    image = models.ImageField(upload_to='user-images/', null=True, blank=True)
    bijouterie = models.ForeignKey(Bijouterie, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees",)
    description = models.TextField(null=True, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    joined_at = models.DateTimeField(default=timezone.now,help_text="Date d’entrée dans l’entreprise",)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Employé"
        verbose_name_plural = "Employés"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["phone"]),
            models.Index(fields=["active"]),
        ]

    def employee_image(self):
        if self.image and hasattr(self.image, "url"):
            return mark_safe(f'<img src="{self.image.url}" width="50" height="50" '
                            'style="object-fit:cover;border-radius:6px;" />')
        return "—"
    employee_image.short_description = "Photo"

    def __str__(self):
        return self.name or f"Employé #{self.pk}"