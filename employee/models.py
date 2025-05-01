from django.db import models
from django.utils.html import mark_safe

from store.models import Bijouterie
# from userauths.models import user_directory_path


# Create your models here.
class Employee(models.Model):
    name = models.CharField(max_length=100, help_text="Shop Name", null=True, blank=True)
    phone =  models.CharField(max_length=20,unique=True,null=True)
    image = models.ImageField(upload_to='user-images/', blank=True)
    # image = models.ImageField(upload_to=user_directory_path, default="shop-image.jpg", blank=True)
    bijoterie = models.ForeignKey(Bijouterie, on_delete=models.SET_NULL, null=True, blank=True, related_name="vendor_bijoutrie")
    description = models.TextField(null=True, blank=True)
    active = models.BooleanField(default=True)
    date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Employees"

    def employee_image(self):
        return mark_safe('  <img src="%s" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />' % (self.shop_image.url))

    def __str__(self):
        return str(self.name)