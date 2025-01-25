"""
Django settings for backend project.

Generated by 'django-admin startproject' using Django 5.1.3.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.1/ref/settings/
"""

import os
from datetime import timedelta
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
# Sécuriser le SECRET_KEY
SECRET_KEY = 'django-insecure-l0_vam@=nmq2gy4b7+=8izmh(h==!hmp=e^+0_97b&m(&#z77@'
# SECRET_KEY = config('SECRET_KEY')
# SECRET_KEY = os.environ.get('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
# DEBUG = False
DEBUG = True

# ALLOWED_HOSTS = [''127.0.0.1, 'localhost', '51.222.110.64', '.rio-gold.com']
ALLOWED_HOSTS = ['*']


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    #Custom Apps
    'userauths',
    'store',
    'stock',
    'sale',
    'api',
    'vendor',
    
    #Third Party App
    'rest_framework',
    # 'knox',
    'corsheaders',
    'drf_yasg',
    'django_rest_passwordreset',
    # 'qrcode'
]

MIDDLEWARE = [
    
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    # add
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # Add Cors Middle ware here
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

CORS_ALLOWED_ORIGINS = ['http://rio-gold.com/',]
# CORS_ALLOWED_ORIGINS = ['http://rio-gold.com/',]
# CORS_ALLOWED_ORIGINS = ['"http://127.0.0.1:8000",',]



# AUTHENTICATION_BACKENDS = [
#     # 'users.authback.EmailBackend',
#     "django.contrib.auth.backends.ModelBackend", # this line fixed my problem
#     'userauths.auth_backend.EmailPhoneUsernameAuthenticationBackend',
# ]

# ROOT_URLCONF = 'api.urls'

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'

# REST_FRAMEWORK = {
#     'DEFAULT_AUTHENTICATION_CLASSES': ('knox.auth.TokenAuthentication',),
# }

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    )
}   

KNOX_TOKEN_TTL = timedelta(hours=1)

# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.mysql',
#         'NAME': 'jewellery_management',
#         'USER': 'root',
#         'PASSWORD': '',
#         'HOST':'localhost',
#         'PORT':'3306',
#         'OPTIONS': {
#             'sql_mode': 'STRICT_ALL_TABLES',
#         },
#     }
# }

# U2ymRZYjZCAk

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# the email settings
#EMAIL configuration
# EMAIL_USE_TLS = True
# EMAIL_HOST = 'smtp.gmail.com'
# EMAIL_PORT = 587
# EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
# EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')

EMAIL_HOST ='smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_HOST_USER = 'lamzooo555@gmail.com'
EMAIL_HOST_PASSWORD = 'zyzruylpncztuqrn'
EMAIL_USE_TLS = True

# DEFAULT_FROM_EMAIL = 'no-reply@yourdomain.com'
# EMAIL_HOST_USER = os.environ.get('EMAIL_USER')
# EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_PASSWORD')
# DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
# EMAIL_HOST_USER = config('EMAIL_HOST_USER')
# EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
# DEFAULT_FROM_EMAIL = 'Diouf7AH'


# FROM_EMAIL = "'bijouterieriogold@gmail.com'"   
# EMAIL_BACKEND = "anymail.backends.mailgun.EmailBackend"
# DEFAULT_FROM_EMAIL = "'bijouterieriogold@gmail.com'"
# SERVER_EMAIL = "'bijouterieriogold@gmail.com'"

# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

# STATIC_URL = 'static/'
# STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

STATIC_URL = 'static/'

# MEDIA_URL = 'media/'
# MEDIA_ROOT = BASE_DIR / 'media'

# STATICFILES_STORAGE = "whitenoise.storage.CompresseManiStaticFilesStorage"
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# SWAGGER_SETTINGS = {
#     'LOGIN_URL' : '/api/login/',
#     'SECURITY_DEFINITIONS': {
#         'Bearer': {
#             'type': 'apiKey',
#             'name': 'Authorization',
#             'in': 'header'
#         }
#     }
# }

SWAGGER_SETTINGS = {
   'SECURITY_DEFINITIONS': {
      'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header'
      }
   }
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'userauths.User'
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend", # this line fixed my problem
    'userauths.auth_backend.EmailPhoneUsernameAuthenticationBackend',
]

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=1000000),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=60),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
    'UPDATE_LAST_LOGIN': False,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',

    'JTI_CLAIM': 'jti',
}

MEDIA_ROOT = os.path.join(BASE_DIR,'media')
MEDIA_URL = '/media/'

CORS_ALLOW_CREDENTIALS = True

# CORS_ORIGIN_WHITELIST = [
#     'http://localhost:3000',
# ]

CORS_ALLOW_METHODS = [
    'GET',
    'POST',
    'PUT',
    'DELETE',
    'OPTIONS',
]

CORS_ALLOW_HEADERS = [
    'content-type',
    'authorization',
    'x-requested-with',
]