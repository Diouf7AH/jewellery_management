import logging
import random
import re
import string
from random import SystemRandom

from django.apps import apps
from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import mark_safe, strip_tags
from django.utils.text import slugify
from django_rest_passwordreset.signals import reset_password_token_created

from store.models import Bijouterie

logger = logging.getLogger(__name__)

GENDER = (
    ("H", "Homme"),
    ("F", "Femme"),
)

# creation des roles
@receiver(post_migrate)
def create_default_instances(sender, **kwargs):
    Role = apps.get_model("userauths", "Role")

    Role.objects.get_or_create(role='admin')
    Role.objects.get_or_create(role='manager')
    Role.objects.get_or_create(role='vendor')
    Role.objects.get_or_create(role='cashier')
    # Role.objects.get_or_create(id=5, defaults={'role': 'simple-user'})
    
# def get_default_role():
#     return Role.objects.get_or_create(id=5, defaults={'role': 'simple-user'})[0].id


# class Role(models.Model):
#     role = models.CharField(max_length=50, unique=True)
    
#     def __str__(self):  
#         return f"{self.role}"
# END Creation

# class UserManager(BaseUserManager):
#     def create_user(self, email, password=None, **extra_fields):
#         if not email:
#             raise ValueError('Email is a required field')

#         email = self.normalize_email(email)
#         extra_fields.setdefault('is_active', True)
#         user = self.model(email=email, **extra_fields)
#         user.set_password(password)
#         user.save(using=self._db)
#         return user

#     def create_superuser(self, email, password=None, **extra_fields):
#         # extra_fields.setdefault('is_staff', True)
#         extra_fields.setdefault('is_superuser', True)
#         extra_fields.setdefault('is_active', True)

#         # if extra_fields.get('is_staff') is not True:
#         #     raise ValueError('Superuser must have is_staff=True.')

#         if extra_fields.get('is_superuser') is not True:
#             raise ValueError('Superuser must have is_superuser=True.')

#         user = self.create_user(email, password, **extra_fields)

#         try:
#             role = Role.objects.get(role='admin')
#         except Role.DoesNotExist:
#             raise ValueError("Le rôle 'admin' n'existe pas dans la table Role.")

#         user.user_role = role
#         user.is_email_verified = True
#         user.save(using=self._db)
#         return user

class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("L'email est obligatoire.")

        email = self.normalize_email(email).lower().strip()
        extra_fields.setdefault("username", email.split("@")[0])

        user = self.model(email=email, **extra_fields)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Le superuser doit avoir is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Le superuser doit avoir is_superuser=True.")

        admin_role, _ = Role.objects.get_or_create(role="admin")
        extra_fields.setdefault("user_role", admin_role)

        return self.create_user(email=email, password=password, **extra_fields)


class Role(models.Model):
    role = models.CharField(max_length=50, unique=True, db_index=True)

    class Meta:
        ordering = ["role"]
        verbose_name = "Rôle"
        verbose_name_plural = "Rôles"

    def __str__(self):
        return self.role


class User(AbstractUser):
    email = models.EmailField(max_length=254, unique=True)
    username = models.CharField(max_length=30, unique=True, null=True, blank=True)
    telephone = models.CharField(max_length=20, unique=True, null=True, blank=True)

    user_role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        related_name="users",
    )

    is_email_verified = models.BooleanField(default=False)
    last_confirmation_email_sent = models.DateTimeField(null=True, blank=True)
    slug = models.SlugField(max_length=20, unique=True, null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["-date_joined"]
        indexes = [
            models.Index(fields=["date_joined"]),
            models.Index(fields=["user_role"]),
            models.Index(fields=["telephone"]),
            models.Index(fields=["email"]),
        ]
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"

    def __str__(self):
        role = getattr(self.user_role, "role", "Aucun rôle")
        return f"{self.email} ({role})"

    @property
    def nom(self):
        return self.last_name

    @property
    def prenom(self):
        return self.first_name

    @property
    def full_name(self):
        return " ".join(filter(None, [self.first_name, self.last_name])).strip()

    @property
    def display_name(self):
        return self.full_name or self.email

    @property
    def role_name(self):
        return (getattr(self.user_role, "role", "") or "").strip().lower()

    @property
    def is_admin(self):
        return self.is_superuser or self.role_name == "admin"

    @property
    def is_manager(self):
        return self.role_name == "manager"

    @property
    def is_vendor(self):
        return self.role_name == "vendor"

    @property
    def is_cashier(self):
        return self.role_name == "cashier"

    @staticmethod
    def random_slug(length=20):
        chars = string.ascii_lowercase + string.digits
        return "".join(random.choices(chars, k=length))

    @classmethod
    def generate_unique_slug(cls, length=20, field_name="slug"):
        for _ in range(20):
            value = cls.random_slug(length=length)
            if not cls.objects.filter(**{field_name: value}).exists():
                return value
        return cls.random_slug(length=length)

    def clean(self):
        super().clean()

        if self.email:
            self.email = self.email.strip().lower()

        if self.username:
            self.username = self.username.strip() or None
        else:
            self.username = None

        if self.telephone:
            t = self.telephone.strip().replace(" ", "")
            if t.startswith("+"):
                t = t[1:]
            if not re.fullmatch(r"\d{9,15}", t):
                raise ValidationError({
                    "telephone": "Le numéro doit contenir 9 à 15 chiffres."
                })
            self.telephone = t
        else:
            self.telephone = None

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()

        if self.username:
            self.username = self.username.strip() or None
        else:
            self.username = None

        if self.telephone:
            t = self.telephone.strip().replace(" ", "")
            if t.startswith("+"):
                t = t[1:]
            self.telephone = t
        else:
            self.telephone = None

        if self.is_superuser and self.user_role_id is None:
            admin_role, _ = Role.objects.get_or_create(role="admin")
            self.user_role = admin_role

        if self.is_admin:
            self.is_staff = True
            self.is_active = True

        if not self.slug:
            self.slug = self.generate_unique_slug()

        super().save(*args, **kwargs)

    def get_full_name(self):
        return self.full_name or self.email

    def get_short_name(self):
        return self.first_name or (self.email.split("@")[0] if self.email else self.slug)
    

def validate_image_size(img):
    if not img:
        return

    max_bytes = 2 * 1024 * 1024
    if img.size > max_bytes:
        raise ValidationError("L'image ne doit pas dépasser 2 Mo.")


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    image = models.ImageField(
        upload_to="users/",
        default="default/default-user.jpg",
        null=True,
        blank=True,
        validators=[validate_image_size],
    )
    bio = models.TextField(blank=True)

    country = models.CharField(max_length=255, null=True, blank=True)
    state = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=255, null=True, blank=True)
    address = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["created_at"]),
        ]
        verbose_name = "Profil"
        verbose_name_plural = "Profils"

    def __str__(self):
        return f"Profil de {self.user.get_full_name() or self.user.email}"

    @property
    def first_name(self):
        return self.user.first_name

    @property
    def last_name(self):
        return self.user.last_name

    @property
    def full_name(self):
        return self.user.get_full_name()
    
    



# class User(AbstractUser):
#     email = models.EmailField(max_length=254, unique=True)
#     username = models.CharField(max_length=30, unique=True, null=True, blank=True)
#     user_role  = models.ForeignKey("Role", on_delete=models.SET_NULL, null=True, db_index=True)
#     is_email_verified = models.BooleanField(default=False)
#     last_confirmation_email_sent = models.DateTimeField(null=True, blank=True)

#     slug = models.SlugField(max_length=20, unique=True, null=True, blank=True)

#     objects = UserManager()
#     USERNAME_FIELD = 'email'
#     REQUIRED_FIELDS = []

#     class Meta:
#         indexes = [
#             models.Index(fields=["created_at"]),
#             models.Index(fields=["user_role"]),
#         ]

#     def __str__(self):
#         role = getattr(self.user_role, "role", "Aucun rôle")
#         return f"{self.email} ({role})"

#     # ---------- Slug helpers ----------

#     @staticmethod
#     def random_slug(length=20):
#         """
#         Génère un slug alphanumérique aléatoire (a-z0-9) de longueur donnée.
#         """
#         chars = string.ascii_lowercase + string.digits
#         return ''.join(random.choices(chars, k=length))

#     @classmethod
#     def generate_unique_slug(cls, length=20, field_name="slug"):
#         """
#         Génère un slug aléatoire unique pour le modèle User.
#         """
#         for _ in range(20):  # on essaie 20 fois max
#             slug = cls.random_slug(length=length)
#             if not cls.objects.filter(**{field_name: slug}).exists():
#                 return slug
#         # fallback ultra improbable
#         return cls.random_slug(length=length)

#     # ---------- Validation ----------

#     def clean(self):
#         super().clean()
#         if self.telephone:
#             t = self.telephone.strip().replace(" ", "")
#             if t.startswith("+"):
#                 t = t[1:]
#             if not re.fullmatch(r"\d{9,15}", t):
#                 raise ValidationError({"telephone": "Le numéro doit contenir 9 à 15 chiffres."})
#             self.telephone = t

#     def save(self, *args, **kwargs):
#         # Admins = staff
#         if self.is_superuser or (self.user_role and self.user_role.role == 'admin'):
#             self.is_staff = True
#             self.is_active = True
#         else:
#             self.is_staff = False

#         if self.email:
#             self.email = self.email.strip().lower()
#         if self.telephone:
#             self.telephone = self.telephone.strip()

#         # Génération du slug aléatoire si absent
#         if not self.slug:
#             # on génère un slug unique avant de sauver
#             self.slug = User.generate_unique_slug()

#         # Sauvegarde normale
#         super().save(*args, **kwargs)

#     # (facultatif)
#     def get_full_name(self):
#         return " ".join(filter(None, [self.first_name, self.last_name])).strip() or self.email

#     def get_short_name(self):
#         return self.first_name or (self.email.split("@")[0] if self.email else self.slug)




# def validate_image_size(img):
#     # 2 Mo max (exemple)
#     max_bytes = 2 * 1024 * 1024
#     if img and hasattr(img, 'size') and img.size > max_bytes:
#         raise ValidationError("L'image ne doit pas dépasser 2 Mo.")

# class Profile(models.Model):
#     user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
#     image = models.ImageField(
#         upload_to="users",
#         default="default/default-user.jpg",
#         null=True, blank=True,
#         validators=[validate_image_size],
#     )
#     bio = models.TextField(blank=True)

#     country = models.CharField(max_length=255, null=True, blank=True)
#     state   = models.CharField(max_length=255, null=True, blank=True)
#     city    = models.CharField(max_length=255, null=True, blank=True)
#     address = models.CharField(max_length=255, null=True, blank=True)

#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         ordering = ["-created_at"]
#         indexes  = [
#             models.Index(fields=["user"]),
#             models.Index(fields=["created_at"]),
#         ]
#         verbose_name = "Profil"
#         verbose_name_plural = "Profils"

#     def __str__(self):
#         fn = (self.user.first_name or "").strip()
#         ln = (self.user.last_name or "").strip()
#         name = f"{fn} {ln}".strip() or self.user.email
#         return f"Profil de {name}"

#     @property
#     def first_name(self):
#         return self.user.first_name

#     @property
#     def last_name(self):
#         return self.user.last_name

#     @property
#     def full_name(self):
#         return f"{self.user.first_name} {self.user.last_name}".strip()

    
    # def __str__(self):
    #     if self.full_name:
    #         return str(self.full_name)
    #     else:
    #         return f"{self.user.first_name} {self.user.last_name}"
    
    # def save(self, *args, **kwargs):
    #     if self.full_name == "" or self.full_name == None:
    #         self.full_name = self.user.full_name
        
    #     super(Profile, self).save(*args, **kwargs)


    def thumbnail(self):
        return mark_safe('<img src="/media/%s" width="50" height="50" object-fit:"cover" style="border-radius: 30px; object-fit: cover;" />' % (self.image))
    
    
    def create_user_profile(sender, instance, created, **kwargs):
        if created:
            Profile.objects.create(user=instance)

    def save_user_profile(sender, instance, **kwargs):
        instance.profile.save()

    @receiver(post_save, sender=User)
    def create_user_profile(sender, instance, created, **kwargs):
        if created:
            Profile.objects.create(user=instance)

    @receiver(post_save, sender=User)
    def save_user_profile(sender, instance, **kwargs):
        if hasattr(instance, "profile"):
            instance.profile.save()

# End Profile


# Mini file d’attente + retry
class OutboxEmail(models.Model):
    to = models.EmailField()
    template = models.CharField(max_length=100)      # ex: "confirm_email"
    context = models.JSONField(default=dict)         # {user_id, confirm_url, home_url}
    reason = models.TextField(blank=True)
    attempts = models.IntegerField(default=0)
    next_try_at = models.DateTimeField(default=timezone.now)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["next_try_at", "to"])]