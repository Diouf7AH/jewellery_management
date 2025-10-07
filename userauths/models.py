from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.mail import EmailMultiAlternatives
import string
from random import SystemRandom
import re
from django.db import models, transaction, IntegrityError
from django.utils.text import slugify
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import mark_safe, strip_tags
from django_rest_passwordreset.signals import reset_password_token_created
from django.core.exceptions import ValidationError
from store.models import Bijouterie
from django.conf import settings
import logging
logger = logging.getLogger(__name__)

GENDER = (
    ("H", "Homme"),
    ("F", "Femme"),
)

# creation des roles
@receiver(post_migrate)
def create_default_instances(sender, **kwargs):
    Role.objects.get_or_create(id=1, defaults={'role': 'admin'})
    Role.objects.get_or_create(id=2, defaults={'role': 'manager'})
    Role.objects.get_or_create(id=3, defaults={'role': 'vendor'})
    Role.objects.get_or_create(id=4, defaults={'role': 'cashier'})
    # Role.objects.get_or_create(id=5, defaults={'role': 'simple-user'})
    
# def get_default_role():
#     return Role.objects.get_or_create(id=5, defaults={'role': 'simple-user'})[0].id


class Role(models.Model):
    role = models.CharField(max_length=50, unique=True)
    
    def __str__(self):  
        return f"{self.role}"
# END Creation

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is a required field')

        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', True)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        # extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        # if extra_fields.get('is_staff') is not True:
        #     raise ValueError('Superuser must have is_staff=True.')

        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        user = self.create_user(email, password, **extra_fields)

        try:
            role = Role.objects.get(role='admin')
        except Role.DoesNotExist:
            raise ValueError("Le rôle 'admin' n'existe pas dans la table Role.")

        user.user_role = role
        user.is_email_verified = True
        user.save(using=self._db)
        return user
    
# class UserManager(BaseUserManager): 
#     def create_user(self, email, password=None, **extra_fields ): 
#         if not email: 
#             raise ValueError('Email is a required field')
        
#         email = self.normalize_email(email)
#         user = self.model(email=email, **extra_fields)
#         user.set_password(password)
#         user.save(using=self._db)
#         return user

#     def create_superuser(self,email, password=None, **extra_fields): 
#         extra_fields.setdefault('is_staff', True)
#         extra_fields.setdefault('is_superuser', True)
#         # return self.create_user(email, password, **extra_fields)
#         user = self.create_user(email, password, **extra_fields)
#         role = Role.objects.get(role='admin')
#         user.user_role = role
#         user.is_email_verified=True
#         user.save()
#         return user

# class User(AbstractUser):
#     email = models.EmailField(max_length=50, unique=True)
#     dateNaiss = models.DateField(null=True, blank=True)
#     username = models.CharField(max_length=30, unique=True, null=True, blank=True)
#     first_name =  models.CharField(max_length=100, blank=True, null=True)
#     last_name =  models.CharField(max_length=100, blank=True, null=True)
#     # phone =  models.CharField(max_length=20,unique=True,null=True,blank=True)
#     telephone = models.CharField(max_length=15, unique=True, null=True, blank=True)
#     is_active = models.BooleanField(default=True)
#     # is_validate = models.BooleanField(default=False)
#     # is_admin = models.BooleanField(default=False)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
#     # bijouterie = models.ForeignKey(Bijouterie, on_delete=models.SET_NULL, null=True, related_name="user_bijouterie")
#     # user_role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, default=get_default_role)
#     user_role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True)
#     is_email_verified = models.BooleanField(default=False)
#     last_confirmation_email_sent = models.DateTimeField(null=True, blank=True)
    
#     objects = UserManager()

#     USERNAME_FIELD = 'email'
#     REQUIRED_FIELDS = []

#     def save(self, *args, **kwargs):
#         if self.user_role and self.user_role.role == 'admin':
#             self.is_active = True
#         super(User, self).save(*args, **kwargs)

#     def __str__(self):
#         return f"{self.email} ({self.user_role.role if self.user_role else 'Aucun rôle'})"

#     def has_perm(self, perm, obj=None):
#         return self.is_superuser or (self.user_role and self.user_role.role == 'admin')

#     def has_module_perms(self, app_label):
#         return self.is_superuser or (self.user_role and self.user_role.role == 'admin')
    
#     # @property
#     # def is_staff(self):
#     #     "Is the user a member of staff?"
#     #     # Simplest possible answer: All admins are staff
#     #     return self.user_role.role == 'admin'
#     @property
#     def is_staff(self):
#         return self.user_role and self.user_role.role == 'admin'

# class User(AbstractUser):
#     email = models.EmailField(max_length=254, unique=True)
#     dateNaiss = models.DateField(null=True, blank=True)
#     username = models.CharField(max_length=30, unique=True, null=True, blank=True)
#     first_name = models.CharField(max_length=100, blank=True, null=True)
#     last_name = models.CharField(max_length=100, blank=True, null=True)
#     telephone = models.CharField(max_length=15, unique=True, null=True, blank=True)
#     is_active = models.BooleanField(default=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
#     user_role = models.ForeignKey("Role", on_delete=models.SET_NULL, null=True)
#     is_email_verified = models.BooleanField(default=False)
#     last_confirmation_email_sent = models.DateTimeField(null=True, blank=True)

#     # ➕ Nouveau champ
#     # slug = models.SlugField(unique=True, max_length=20, null=False, blank=True) # EN PROD
#     # slug = models.SlugField(max_length=20, unique=True)  # sans null=True / blank=True
#     slug = models.SlugField(max_length=20, unique=True, null=True, blank=True)  # TEMPORAIRE

#     objects = UserManager()

#     USERNAME_FIELD = 'email'
#     REQUIRED_FIELDS = []

#     def __str__(self):
#         return f"{self.email} ({self.user_role.role if self.user_role else 'Aucun rôle'})"

#     # --------------------
#     # 🔑 Génération du slug
#     # --------------------
#     def generate_slug(self):
#         """Construit un slug unique basé sur prénom/nom/email"""
#         if self.first_name or self.last_name:
#             base_txt = "-".join(filter(None, [self.first_name, self.last_name]))
#         elif self.username:
#             base_txt = self.username
#         elif self.email:
#             base_txt = self.email.split("@")[0]
#         else:
#             base_txt = "user"

#         base = slugify(base_txt).lower()[:14].rstrip("-") or "user"
#         suffix = ''.join(SystemRandom().choices(string.digits, k=4))
#         return f"{base}-{suffix}"[:20]

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
#         # Règles staff/admin
#         if self.is_superuser:
#             self.is_staff = True
#         elif self.user_role and self.user_role.role == 'admin':
#             self.is_staff = True
#             self.is_active = True
#         else:
#             self.is_staff = False

#         # Normalisation email/téléphone
#         if self.email:
#             self.email = self.email.strip().lower()
#         if self.telephone:
#             self.telephone = self.telephone.strip()

#         # 🔥 Génération slug si absent
#         if not self.slug:
#             for attempt in range(10):
#                 candidate = self.generate_slug()
#                 self.slug = candidate
#                 try:
#                     with transaction.atomic():
#                         super().save(*args, **kwargs)
#                     break
#                 except IntegrityError:
#                     self.slug = None
#             else:
#                 # Dernier recours : slug totalement random
#                 self.slug = ''.join(SystemRandom().choices(string.ascii_lowercase + string.digits, k=20))
#                 super().save(*args, **kwargs)
#         else:
#             super().save(*args, **kwargs)

#     def has_perm(self, perm, obj=None):
#         return self.is_superuser or (self.user_role and self.user_role.role == 'admin')

#     def has_module_perms(self, app_label):
#         return self.is_superuser or (self.user_role and self.user_role.role == 'admin')


class User(AbstractUser):
    email = models.EmailField(max_length=254, unique=True)
    dateNaiss = models.DateField(null=True, blank=True)
    username = models.CharField(max_length=30, unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name  = models.CharField(max_length=100, blank=True, null=True)
    telephone  = models.CharField(max_length=15, unique=True, null=True, blank=True)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user_role  = models.ForeignKey("Role", on_delete=models.SET_NULL, null=True, db_index=True)
    is_email_verified = models.BooleanField(default=False)
    last_confirmation_email_sent = models.DateTimeField(null=True, blank=True)

    slug = models.SlugField(max_length=20, unique=True, null=True, blank=True)  # ⇒ passera à not null plus tard

    objects = UserManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["user_role"]),
        ]

    def __str__(self):
        role = getattr(self.user_role, "role", "Aucun rôle")
        return f"{self.email} ({role})"

    def generate_slug(self):
        if self.first_name or self.last_name:
            base_txt = "-".join(filter(None, [self.first_name, self.last_name]))
        elif self.username:
            base_txt = self.username
        elif self.email:
            base_txt = self.email.split("@")[0]
        else:
            base_txt = "user"
        base = slugify(base_txt).lower()[:14].rstrip("-") or "user"
        suffix = ''.join(SystemRandom().choices(string.digits, k=4))
        return f"{base}-{suffix}"[:20]

    def clean(self):
        super().clean()
        if self.telephone:
            t = self.telephone.strip().replace(" ", "")
            if t.startswith("+"):
                t = t[1:]
            if not re.fullmatch(r"\d{9,15}", t):
                raise ValidationError({"telephone": "Le numéro doit contenir 9 à 15 chiffres."})
            self.telephone = t

    def save(self, *args, **kwargs):
        # Admins = staff
        if self.is_superuser or (self.user_role and self.user_role.role == 'admin'):
            self.is_staff = True
            self.is_active = True
        else:
            # garde ou non la ligne ci-dessous selon ta politique
            self.is_staff = False

        if self.email:
            self.email = self.email.strip().lower()
        if self.telephone:
            self.telephone = self.telephone.strip()

        if not self.slug:
            for _ in range(10):
                self.slug = self.generate_slug()
                try:
                    with transaction.atomic():
                        super().save(*args, **kwargs)
                    break
                except IntegrityError:
                    self.slug = None
            else:
                self.slug = ''.join(SystemRandom().choices(string.ascii_lowercase + string.digits, k=20))
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    # (facultatif)
    def get_full_name(self):
        return " ".join(filter(None, [self.first_name, self.last_name])).strip() or self.email

    def get_short_name(self):
        return self.first_name or (self.email.split("@")[0] if self.email else self.slug)



# def send_password_reset_email(reset_password_token):
#     sitelink = getattr(settings, "FRONTEND_URL", "http://localhost:5173/")
#     full_link = f"https://rio-gold.com/password-reset/{reset_password_token.key}"
#     full_link = f"{sitelink.rstrip('/')}/password-reset/{reset_password_token.key}"

#     context = {
#         'full_link': full_link,
#         'email_address': reset_password_token.user.email
#     }

#     html_message = render_to_string("backend/email.html", context=context)
#     plain_message = strip_tags(html_message)

#     try:
#         msg = EmailMultiAlternatives(
#             subject="Réinitialisation de votre mot de passe",
#             body=plain_message,
#             from_email=settings.DEFAULT_FROM_EMAIL,
#             to=[reset_password_token.user.email]
#         )
#         msg.attach_alternative(html_message, "text/html")
#         msg.send(fail_silently=False)
#         logger.info("Email envoyé avec succès.")
#     except Exception as e:
#         logger.error(f"Erreur d'envoi de l'email : {e}")
        

# def send_password_reset_email(reset_password_token):
#     sitelink = getattr(settings, "FRONTEND_URL", "http://localhost:5173/")
#     full_link = f"{sitelink.rstrip('/')}/password-reset/{reset_password_token.key}"

#     context = {
#         'full_link': full_link,
#         'email_address': reset_password_token.user.email
#     }

#     html_message = render_to_string("backend/email.html", context=context)
#     plain_message = strip_tags(html_message)

#     try:
#         msg = EmailMultiAlternatives(
#             subject="Réinitialisation de votre mot de passe",
#             body=plain_message,
#             from_email=settings.DEFAULT_FROM_EMAIL,
#             to=[reset_password_token.user.email]
#         )
#         msg.attach_alternative(html_message, "text/html")
#         msg.send()
#         logger.info("Email envoyé avec succès.")
#     except Exception as e:
#         logger.error(f"Erreur d'envoi de l'email : {e}")
        

# password
# @receiver(reset_password_token_created)
# def password_reset_token_created(reset_password_token, *args, **kwargs):
#     sitelink = "http://localhost:5173/"
#     token = "{}".format(reset_password_token.key)
#     full_link = str(sitelink)+str("password-reset/")+str(token)

#     print(token)
#     print(full_link)

#     context = {
#         'full_link': full_link,
#         'email_address': reset_password_token.user.email
#     }

#     html_message = render_to_string("backend/email.html", context=context)
#     plain_message = strip_tags(html_message)

#     msg = EmailMultiAlternatives(
#         subject = "Request for resetting password for {title}".format(title=reset_password_token.user.email), 
#         body=plain_message,
#         from_email = "sender@example.com", 
#         to=[reset_password_token.user.email]
#     )

#     msg.attach_alternative(html_message, "text/html")
#     msg.send()


# # Profile
# class Profile(models.Model):
#     user = models.OneToOneField(User, on_delete=models.CASCADE)
#     image = models.ImageField(upload_to='users', default='default/default-user.jpg', null=True, blank=True)
#     # full_name = models.CharField(max_length=1000, null=True, blank=True)
#     bio = models.TextField(blank=True)
    
#     gender = models.CharField(max_length=1, choices=GENDER, null=True, blank=True)
#     country = models.CharField(max_length=255, null=True, blank=True)
#     city = models.CharField(max_length=255, null=True, blank=True)
#     state = models.CharField(max_length=255, null=True, blank=True)
#     address = models.CharField(max_length=255, null=True, blank=True)
#     # newsletter = models.BooleanField(default=False)
#     # type = models.CharField(max_length=500, choices=GENDER, null=True, blank=True)
#     date = models.DateTimeField(auto_now_add=True, null=True, blank=True)
#     # pid = ShortUUIDField(unique=True, length=10, max_length=20, alphabet="abcdefghijklmnopqrstuvxyz")


#     class Meta:
#         ordering = ["-date"]

#     def __str__(self):
#         return f"{self.user.first_name} {self.user.last_name}"

class Sex(models.TextChoices):
    M = "M", "Homme"
    F = "F", "Femme"

def validate_image_size(img):
    # 2 Mo max (exemple)
    max_bytes = 2 * 1024 * 1024
    if img and hasattr(img, 'size') and img.size > max_bytes:
        raise ValidationError("L'image ne doit pas dépasser 2 Mo.")

class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    image = models.ImageField(
        upload_to="users",
        default="default/default-user.jpg",
        null=True, blank=True,
        validators=[validate_image_size],
    )
    bio = models.TextField(blank=True)

    sex  = models.CharField(max_length=1, choices=Sex.choices, null=True, blank=True)
    country = models.CharField(max_length=255, null=True, blank=True)
    state   = models.CharField(max_length=255, null=True, blank=True)
    city    = models.CharField(max_length=255, null=True, blank=True)
    address = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes  = [
            models.Index(fields=["user"]),
            models.Index(fields=["created_at"]),
        ]
        verbose_name = "Profil"
        verbose_name_plural = "Profils"

    def __str__(self):
        fn = (self.user.first_name or "").strip()
        ln = (self.user.last_name or "").strip()
        name = f"{fn} {ln}".strip() or self.user.email
        return f"Profil de {name}"

    @property
    def first_name(self):
        return self.user.first_name

    @property
    def last_name(self):
        return self.user.last_name

    @property
    def full_name(self):
        return f"{self.user.first_name} {self.user.last_name}".strip()

    
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

post_save.connect(create_user_profile, sender=User)
post_save.connect(save_user_profile, sender=User)

# End Profile