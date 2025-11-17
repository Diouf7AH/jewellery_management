# version angular
# from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
# from django.conf import settings


# SALT_EMAIL_CONFIRMATION = "email-confirmation"


# def _get_serializer() -> URLSafeTimedSerializer:
#     """
#     Retourne un serializer itsdangerous basé sur SECRET_KEY.
#     """
#     return URLSafeTimedSerializer(settings.SECRET_KEY)


# def generate_email_token(user) -> str:
#     """
#     Génère un token de confirmation à partir de l'email de l'utilisateur.
#     """
#     s = _get_serializer()
#     email_norm = (user.email or "").strip().lower()
#     return s.dumps(email_norm, salt=SALT_EMAIL_CONFIRMATION)


# def verify_email_token(token: str, expiration: int | None = None) -> dict:
#     """
#     Vérifie le token de confirmation.
#     Retourne un dict :
#       - {"status": "valid", "email": "<email>"}  si OK
#       - {"status": "expired", "email": None}     si expiré
#       - {"status": "invalid", "email": None}     si signature invalide

#     `expiration` est en secondes. Si None → prend settings.EMAIL_TOKEN_EXPIRATION
#     (par défaut 3600s dans ton settings).
#     """
#     if expiration is None:
#         expiration = getattr(settings, "EMAIL_TOKEN_EXPIRATION", 3600)

#     s = _get_serializer()
#     try:
#         email = s.loads(
#             token,
#             salt=SALT_EMAIL_CONFIRMATION,
#             max_age=expiration,
#         )
#         # Normalise l'email
#         email = (email or "").strip().lower()
#         return {"status": "valid", "email": email}
#     except SignatureExpired:
#         return {"status": "expired", "email": None}
#     except BadSignature:
#         return {"status": "invalid", "email": None}