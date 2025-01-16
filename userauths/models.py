from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags
from django_rest_passwordreset.signals import reset_password_token_created

from store.models import Bijouterie


@receiver(post_migrate)
def create_default_instances(sender, **kwargs):
    Role.objects.get_or_create(id=1, defaults={'role': 'admin'})
    Role.objects.get_or_create(id=2, defaults={'role': 'manager'})
    Role.objects.get_or_create(id=3, defaults={'role': 'vendeur'})
    Role.objects.get_or_create(id=4, defaults={'role': 'caissier'})


class Role(models.Model):
    role = models.CharField(max_length=50)
    
    def __str__(self):  
        return f"{self.role}"


class UserManager(BaseUserManager): 
    def create_user(self, email, password=None, **extra_fields ): 
        if not email: 
            raise ValueError('Email is a required field')
        
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self,email, password=None, **extra_fields): 
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        # return self.create_user(email, password, **extra_fields)
        user = self.create_user(email, password, **extra_fields)
        role = Role.objects.get(role='admin')
        user.user_role = role
        user.save()
        return user

class User(AbstractUser):
    email = models.EmailField(max_length=200, unique=True)
    dateNaiss = models.DateField(null=True, blank=True)
    username = models.CharField(max_length=200, null=True, blank=True)
    firstname =  models.CharField(max_length=200, blank=True, null=True)
    lastname =  models.CharField(max_length=200, blank=True, null=True)
    phone =  models.CharField(max_length=20,unique=True,null=True)
    address = models.TextField(default="")
    is_active = models.BooleanField(default=True)
    # is_admin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    bijouterie = models.ForeignKey(Bijouterie, on_delete=models.SET_NULL, null=True, related_name="user_bijouterie")
    user_role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []


@receiver(reset_password_token_created)
def password_reset_token_created(reset_password_token, *args, **kwargs):
    sitelink = "http://localhost:5173/"
    token = "{}".format(reset_password_token.key)
    full_link = str(sitelink)+str("password-reset/")+str(token)

    print(token)
    print(full_link)

    context = {
        'full_link': full_link,
        'email_adress': reset_password_token.user.email
    }

    html_message = render_to_string("backend/email.html", context=context)
    plain_message = strip_tags(html_message)

    msg = EmailMultiAlternatives(
        subject = "Request for resetting password for {title}".format(title=reset_password_token.user.email), 
        body=plain_message,
        from_email = "sender@example.com", 
        to=[reset_password_token.user.email]
    )

    msg.attach_alternative(html_message, "text/html")
    msg.send()
