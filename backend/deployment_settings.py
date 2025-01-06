# import os

# import dj_database_url

# from .settings import *
# from .settings import BASE_DIR

# ALLOWED_HOSTS = [os.environ.get('RENDER_EXTERNAL_HOSTNAME')]
# CSRF_TRUSTED_ORIGINS = ['https://'+os.environ.get('RENDER_EXTERNAL_HOSTNAME')]

# DEBUG = False
# SECRET_KEY = os.environ.get('SECRET_KEY')

# MIDDLEWARE = [
#     'corsheaders.middleware.CorsMiddleware',
#     'django.middleware.security.SecurityMiddleware',
#     # Add Cors Middle ware here
#     'whitenoise.middleware.WhiteNoiseMiddleware',
#     'django.contrib.sessions.middleware.SessionMiddleware',
#     'django.middleware.common.CommonMiddleware',
#     'django.middleware.csrf.CsrfViewMiddleware',
#     'django.contrib.auth.middleware.AuthenticationMiddleware',
#     'django.contrib.messages.middleware.MessageMiddleware',
#     'django.middleware.clickjacking.XFrameOptionsMiddleware',
# ]

# # CORS_ALLOWED_ORIGINS = [
# #     'https://rio-gold.com'
# # ]

# STORAGES = {
#     "default":{
#         "BACKEND" : "django.core.files.storage.FileSystemStorage",
#     },
#     "staticfiles": {
#         "BACKEND" : "whitenoise.storage.CompressedStaticFilesStorage",
#     },

# }

# DATABASES = {
#     'default': dj_database_url.config(
#         default= os.environ['DATABASE_URL'], 
#         conn_max_age=600
#     )
# }

# # ADMINS = [("Diouf7AH", "lamzooo555@gmail.com")]

# # EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# # EMAIL_HOST = 'smtp.gmail.com'
# # EMAIL_PORT = 587
# # EMAIL_USE_TLS = True
# # EMAIL_HOST_USER = os.environ.get('EMAIL_USER')
# # EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_PASSWORD')
# # DEFAULT_FROM_EMAIL = 'default from email'