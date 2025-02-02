from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import mark_safe, strip_tags
from django_rest_passwordreset.signals import reset_password_token_created

from store.models import Bijouterie

GENDER = (
    ("H", "Homme"),
    ("F", "Femme"),
)

# creation des roles
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
# END Creation


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
        # extra_fields.setdefault('is_staff', True)
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
    first_name =  models.CharField(max_length=200, blank=True, null=True)
    last_name =  models.CharField(max_length=200, blank=True, null=True)
    phone =  models.CharField(max_length=20,unique=True,null=True)
    is_active = models.BooleanField(default=True)
    # is_admin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    bijouterie = models.ForeignKey(Bijouterie, on_delete=models.SET_NULL, null=True, related_name="user_bijouterie")
    user_role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def save(self, *args, **kwargs):
        if self.user_role and self.user_role.role == 'admin':
            self.active = True
        super(User, self).save(*args, **kwargs)

    def __str__(self) ->str:
        return str(self.email)

    # def has_perm(self, perm, obj=None):
    #     "Does the user have a specific permission?"
    #     # Simplest possible answer: Yes, always
    #     return self.user.role.is_admin

    # def has_module_perms(self, app_label):
    #     "Does the user have permissions to view the app `app_label`?"
    #     # Simplest possible answer: Yes, always
    #     return True

    # @property
    # def is_staff(self):
    #     "Is the user a member of staff?"
    #     # Simplest possible answer: All admins are staff
    #     return self.user_role.role == 'admin'


# path for image
def user_directory_path(instance, filename):
    user = None
    
    if hasattr(instance, 'user') and instance.user:
        user = instance.user
    elif hasattr(instance, 'vendor') and hasattr(instance.vendor, 'user') and instance.vendor.user:
        user = instance.vendor.user
    elif hasattr(instance, 'produit') and hasattr(instance.produit.vendor, 'user') and instance.produit.vendor.user:
        user = instance.produit.vendor.user

    if user:
        ext = filename.split('.')[-1]
        filename = "%s.%s" % (user.id, ext)
        return 'user_{0}/{1}'.format(user.id, filename)
    else:
        # Handle the case when user is None
        # You can return a default path or raise an exception, depending on your requirements.
        # For example, return a path with 'unknown_user' as the user ID:
        ext = filename.split('.')[-1]
        filename = "%s.%s" % ('file', ext)
        return 'user_{0}/{1}'.format('file', filename)


# password
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


# # Profile
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to='users', default='default/default-user.jpg', null=True, blank=True)
    # full_name = models.CharField(max_length=1000, null=True, blank=True)
    bio = models.TextField(blank=True)
    
    gender = models.CharField(max_length=1, choices=GENDER, null=True, blank=True)
    country = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=255, null=True, blank=True)
    state = models.CharField(max_length=255, null=True, blank=True)
    address = models.CharField(max_length=255, null=True, blank=True)
    # newsletter = models.BooleanField(default=False)
    # wishlist = models.ManyToManyField("store.Product", blank=True)
    # type = models.CharField(max_length=500, choices=GENDER, null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    # pid = ShortUUIDField(unique=True, length=10, max_length=20, alphabet="abcdefghijklmnopqrstuvxyz")


    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name}"
    
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