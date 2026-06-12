# from django.conf import settings
# from django.db.models.signals import post_save
# from django.dispatch import receiver
# from django_rest_passwordreset.signals import reset_password_token_created
# from django.contrib.auth import get_user_model
# from django.db.models.signals import post_save
# from django.dispatch import receiver

# from .models import Profile

# User = get_user_model()
# from .models import Profile
# from .utils import send_password_reset_email
    
# # @receiver(reset_password_token_created)
# # def password_reset_token_created_handler(sender, instance, reset_password_token, *args, **kwargs):
# #     send_password_reset_email(sender, instance, reset_password_token, *args, **kwargs)
# @receiver(
#     reset_password_token_created,
#     dispatch_uid="userauths_password_reset_token_created"
# )
# def password_reset_token_created_handler(sender, instance, reset_password_token, *args, **kwargs):
#     # Optionnel : protéger contre les erreurs d’envoi email
#     try:
#         send_password_reset_email(sender, instance, reset_password_token, *args, **kwargs)
#     except Exception:
#         # logguer proprement (sentry, logging, etc.)
#         # logging.exception("Erreur envoi email reset password")
#         pass


# # Comme ton modèle User possède déjà first_name / last_name, 
# # le plus propre est de ne pas dupliquer 
# # ces champs sur Profile, mais d’y accéder via des champs “proxy”
# # dispatch_uid garantit qu’un même signal ne sera pas connecté plusieurs fois 
# # si le module est importé plus d’une fois (reloader, tests, Celery, etc.).
# @receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid="userauths_create_profile")
# def create_profile_for_new_user(sender, instance, created, **kwargs):
#     if created:
#         Profile.objects.get_or_create(user=instance)


    


# @receiver(post_save, sender=User)
# def create_user_profile(sender, instance, created, **kwargs):
#     if created:
#         Profile.objects.get_or_create(user=instance)



from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django_rest_passwordreset.signals import reset_password_token_created

from .models import Profile
from .utils import send_password_reset_email


@receiver(
    reset_password_token_created,
    dispatch_uid="userauths_password_reset_token_created"
)
def password_reset_token_created_handler(sender, instance, reset_password_token, *args, **kwargs):
    try:
        send_password_reset_email(sender, instance, reset_password_token, *args, **kwargs)
    except Exception:
        pass


@receiver(
    post_save,
    sender=settings.AUTH_USER_MODEL,
    dispatch_uid="userauths_create_profile"
)
def create_profile_for_new_user(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)
        
        


