from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from userauths.utils import verify_email_token
from userauths.models import User
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from datetime import timedelta
from django.core.mail import send_mail
from django.urls import reverse
from django.contrib.auth import get_user_model
from userauths.utils import verify_email_token

User = get_user_model()

# Email-registrer
# def verify_email_token(token, expiration=3600):
#     serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
#     try:
#         email = serializer.loads(token, salt="email-confirmation", max_age=expiration)
#         return email
#     except Exception:
#         return None
# def verify_email_token(token, expiration=86400):  # 24h
#     serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
#     try:
#         email = serializer.loads(token, salt="email-confirmation", max_age=expiration)
#         return email
#     except Exception:
#         return None

# # Email-register
# # def send_confirmation_email(user, request):
# #     token = generate_email_token(user)
# #     confirm_url = request.build_absolute_uri(
# #         reverse('verify-email') + f"?token={token}"
# #     )
# #     subject = "Confirmez votre adresse email"
# #     message = f"Bonjour {user.username or user.email},\n\nCliquez sur ce lien pour confirmer votre adresse email :\n{confirm_url}"

# #     send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])

# def send_confirmation_email(user, request):
#     token = generate_email_token(user)
#     confirm_url = request.build_absolute_uri(reverse('verify-email') + f"?token={token}")

#     subject = "Confirmez votre adresse email ✉️"
#     from_email = settings.DEFAULT_FROM_EMAIL
#     to_email = [user.email]

#     # Render HTML template
#     html_message = render_to_string("emails/email_confirmation.html", {
#         "user": user,
#         "confirm_url": confirm_url,
#     })

#     email = EmailMultiAlternatives(subject, "", from_email, to_email)
#     email.attach_alternative(html_message, "text/html")
#     email.send()


# Crée une tâche qui relance les utilisateurs non vérifiés depuis > 24h :
# def resend_confirmation_emails():
#     cutoff = timezone.now() - timedelta(hours=24)
#     users = User.objects.filter(is_email_verified=False, date_joined__lt=cutoff)

#     for user in users:
#         send_confirmation_email(user, request=None)  # tu peux injecter une fausse `request` avec ton domaine


class UserRegistrationView(APIView):
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Inscription d’un nouvel utilisateur avec confirmation email",
        request_body=UserRegistrationSerializer,
        responses={
            201: openapi.Response('Inscription réussie', UserDetailSerializer),
            400: openapi.Response('Requête invalide')
        }
    )
    def post(self, request, format=None):
        serializer = UserRegistrationSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        data = {
            'message': "Inscription réussie ✅. Vérifiez votre email.",
            'user': UserDetailSerializer(user).data,
            'tokens': serializer.tokens
        }
        return Response(data, status=status.HTTP_201_CREATED)


class EmailVerificationView(APIView):
    permission_classes = []

    def get(self, request):
        token = request.GET.get('token')
        email = verify_email_token(token)

        if not email:
            return render(request, "emails/email_invalid.html", status=400)

        try:
            user = User.objects.get(email=email)
            if not user.is_email_verified:
                user.is_email_verified = True
                user.save()

            return render(request, "emails/email_confirmed.html")

        except User.DoesNotExist:
            return render(request, "emails/email_invalid.html", status=404)
        

# class EmailVerificationView(APIView):
#     def get(self, request):
#         token = request.GET.get('token')
#         email = verify_email_token(token)

#         if not email:
#             return Response({"error": "Lien invalide ou expiré"}, status=400)

#         try:
#             user = User.objects.get(email=email)
#             if user.is_email_verified:
#                 return Response({"message": "Email déjà vérifié"}, status=200)

#             user.is_email_verified = True
#             user.save()
#             return Response({"message": "Email vérifié avec succès ✅"}, status=200)
#         except User.DoesNotExist:
#             return Response({"error": "Utilisateur introuvable"}, status=404)