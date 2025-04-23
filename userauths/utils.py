import threading
from django.core.mail import EmailMessage

from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.conf import settings
from datetime import datetime

# class EmailThread(threading.Thread):

#     def __init__(self, email):
#         self.email = email
#         threading.Thread.__init__(self)

#     def run(self):
#         self.email.send()


# class Util:
#     @staticmethod
#     def send_email(data):
#         email = EmailMessage(
#             subject=data['email_subject'], body=data['email_body'], to=[data['to_email']])
#         EmailThread(email).start()

# EMAIL

# def verify_email_token(token, expiration=86400):  # 24h
#     serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
#     try:
#         email = serializer.loads(token, salt="email-confirmation", max_age=expiration)
#         return email
#     except Exception:
#         return None


# def generate_email_token(user):
#     serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
#     return serializer.dumps(user.email, salt="email-confirmation")

# def send_confirmation_email(user, request):
#     token = generate_email_token(user)
#     confirm_url = request.build_absolute_uri(reverse('verify-email') + f"?token={token}")
#     subject = "Confirmez votre adresse email"
#     home_url = request.build_absolute_uri('/')
#     html = render_to_string("emails/email_confirmation.html", {
#         "user": user, 
#         "home_url": home_url, 
#         "confirm_url": confirm_url
#         })
#     email = EmailMultiAlternatives(subject, "", settings.DEFAULT_FROM_EMAIL, [user.email])
#     email.attach_alternative(html, "text/html")
#     email.send()



# def generate_email_token(user):
#     serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
#     return serializer.dumps(user.email, salt="email-confirmation")

# # def verify_email_token(token, expiration=86400):  # 24h
# def verify_email_token(token, expiration = getattr(settings, 'EMAIL_TOKEN_EXPIRATION', 10)):  # 24h
#     serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
#     try:
#         email = serializer.loads(token, salt="email-confirmation", max_age=expiration)
#         return {"status": "valid", "email": email}
#     except SignatureExpired:
#         return {"status": "expired", "email": None}
#     except BadSignature:
#         return {"status": "invalid", "email": None}

# def send_confirmation_email(user, request):
#     token = generate_email_token(user)
#     confirm_url = request.build_absolute_uri(reverse('verify-email') + f"?token={token}")
#     home_url = request.build_absolute_uri('/')

#     subject = "Confirmez votre adresse email"
#     html = render_to_string("emails/email_confirmation.html", {
#         "user": user,
#         "home_url": home_url,
#         "confirm_url": confirm_url,
#         "year": datetime.now().year
#     })

#     email = EmailMultiAlternatives(subject, "", settings.DEFAULT_FROM_EMAIL, [user.email])
#     email.attach_alternative(html, "text/html")
#     email.send()


# ✅ Fonction pour générer un token
def generate_email_token(user):
    serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
    return serializer.dumps(user.email, salt="email-confirmation")


# ✅ Fonction pour valider le token
def verify_email_token(token, expiration=getattr(settings, 'EMAIL_TOKEN_EXPIRATION', 60)):
    serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
    try:
        email = serializer.loads(token, salt="email-confirmation", max_age=expiration)
        return {"status": "valid", "email": email}
    except SignatureExpired:
        return {"status": "expired", "email": None}
    except BadSignature:
        return {"status": "invalid", "email": None}


# ✅ Fonction pour envoyer l'email de confirmation
def send_confirmation_email(user, request):
    token = generate_email_token(user)
    confirm_url = request.build_absolute_uri(reverse('verify-email') + f"?token={token}")
    home_url = request.build_absolute_uri('/')

    subject = "Confirmez votre adresse email"
    html = render_to_string("emails/email_confirmation.html", {
        "user": user,
        "home_url": home_url,
        "confirm_url": confirm_url,
        "year": datetime.now().year
    })

    email = EmailMultiAlternatives(subject, "", settings.DEFAULT_FROM_EMAIL, [user.email])
    email.attach_alternative(html, "text/html")
    email.send()
