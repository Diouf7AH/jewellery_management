from django.dispatch import receiver
from django_rest_passwordreset.signals import reset_password_token_created
from userauths.utils import send_password_reset_email  # ← import depuis utils.py

@receiver(reset_password_token_created)
def password_reset_token_created(sender, reset_password_token, *args, **kwargs):
    send_password_reset_email(reset_password_token)