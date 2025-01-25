import string
from random import SystemRandom

from django.db import models
from django.utils.html import mark_safe
from django.utils.text import slugify

from userauths.models import User, user_directory_path


# Create your models here.
class Vendor(models.Model):
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, related_name="vendor")
    image = models.ImageField(upload_to=user_directory_path, default="shop-image.jpg", blank=True)
    nom = models.CharField(max_length=100, help_text="Shop Name", null=True, blank=True)
    # email = models.EmailField(max_length=100, help_text="Shop Email", null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    # mobile = models.CharField(max_length = 150, null=True, blank=True)
    # verified = models.BooleanField(default=False)
    # active = models.BooleanField(default=True)
    # date = models.DateTimeField(auto_now_add=True)
    slug = models.SlugField(unique=True, max_length=50, null=True, blank=True)

    def save(self, *args, **kwargs):
        self.nom = f"{self.user.firstname} {self.user.lastname}"
        if self.slug == "" or self.slug is None:
            rand_letters = ''.join(SystemRandom().choices(string.ascii_letters + string.digits, k=15))
            self.slug = slugify(rand_letters)
        super(Vendor, self).save(*args, **kwargs) 
    
    class Meta:
        verbose_name_plural = "Vendors"

    def vendor_image(self):
        return mark_safe('  <img src="%s" width="50" height="50" style="object-fit:cover; border-radius: 6px;" />' % (self.shop_image.url))

    def __str__(self):
        return str(self.name)
        

    def save(self, *args, **kwargs):
        if self.slug == "" or self.slug == None:
            self.slug = slugify(self.name)
        super(Vendor, self).save(*args, **kwargs) 
