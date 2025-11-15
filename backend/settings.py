# Python 3.10.5
# python -m django --version 4.2
import os
from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Core ---
SECRET_KEY = config('SECRET_KEY', cast=str)
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='127.0.0.1,localhost', cast=Csv())

TIME_ZONE = config('TIME_ZONE', default='UTC')
LANGUAGE_CODE = 'en-us'
USE_I18N = True
USE_TZ = True


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT'),
        'OPTIONS': {
            'sql_mode': 'STRICT_ALL_TABLES',
        },
    }
}


# ALLOWED_HOSTS = ['147.79.100.245', 'rio-gold.com', 'www.rio-gold.com']
#ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '147.79.100.245', 'rio-gold.com', 'www.rio-gold.com']
ALLOWED_HOSTS = ['*']
# ALLOWED_HOSTS = ['localhost', '127.0.0.1']


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    #Custom Apps
    # 'userauths',
    'userauths.apps.UserauthsConfig',
    'store',
    'stock',
    'staff',
    'inventory',
    # 'sale',
    'sale.apps.SaleConfig',
    'api',
    'vendor',
    'employee',
    'purchase',
    'compte_depot',
    'order',
    
    #Third Party App
    'rest_framework',
    # 'knox',
    'corsheaders',
    'drf_yasg',
    'django_rest_passwordreset',
    # 'qrcode'
    'rest_framework_simplejwt.token_blacklist',
    # for list display
    "django_filters",
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

# WSGI_APPLICATION = 'backend.wsgi.application'



# --- DRF (fusion de tes deux blocs) ---
REST_FRAMEWORK = {
    "COERCE_DECIMAL_TO_STRING": True,
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    # "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    # "PAGE_SIZE": 20,
}


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

SITE_URL = "https://www.rio-gold.com"

LANGUAGE_CODE = 'en-us'

# TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

# --- Static / Media ---
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


SWAGGER_SETTINGS = {
    'USE_SESSION_AUTH': False,
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header',
        }
    },
}




# --- Auth / JWT ---
AUTH_USER_MODEL = 'userauths.User'
AUTHENTICATION_BACKENDS = [
    'userauths.auth_backend.EmailPhoneUsernameAuthenticationBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# SIMPLE_JWT = {
#     'ACCESS_TOKEN_LIFETIME': timedelta(minutes=120),
#     'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
#     'ROTATE_REFRESH_TOKENS': True,
#     'BLACKLIST_AFTER_ROTATION': True,
#     'UPDATE_LAST_LOGIN': False,
#     'AUTH_HEADER_TYPES': ('Bearer',),
#     'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
#     'USER_ID_FIELD': 'id',
#     'USER_ID_CLAIM': 'user_id',
#     'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',
#     'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
#     'TOKEN_TYPE_CLAIM': 'token_type',
#     'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',
#     'JTI_CLAIM': 'jti',
# }


SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=120),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}



# CORS_ALLOW_ALL_ORIGINS = True


# CORS_ALLOWED_ORIGINS = [
# 	"http://localhost:4200",
# 	"http://127.0.0.1:4200",
# 	"https://rio-gold.com",
# 	"http://rio-gold.com",
# ]

# CORS_ALLOW_METHODS = [
#     'GET',
#     'POST',
#     'PUT',
#     'DELETE',
#     'OPTIONS',
# ]

# CORS_ALLOW_HEADERS = [
#     'content-type',
#     'authorization',
#     'x-requested-with',
# ]

# --- CORS ---
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='http://localhost:4200,http://127.0.0.1:4200,https://rio-gold.com', cast=Csv())

CORS_ALLOW_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
CORS_ALLOW_HEADERS = ['content-type', 'authorization', 'x-requested-with']


# --- Email ---
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST')
EMAIL_PORT = config('EMAIL_PORT', cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', default=20, cast=int)
# DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default=f"Rio Gold <{EMAIL_HOST_USER}>")




# --- Frontend / URLs (pour tes emails) ---
FRONTEND_BASE_URL = config('FRONTEND_BASE_URL', default='https://rio-gold.com')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', 'Rio Gold <no-reply@rio-gold.com>')
FRONTEND_URL = config('FRONTEND_URL', default='https://rio-gold.com')
EMAIL_TOKEN_EXPIRATION = config('EMAIL_TOKEN_EXPIRATION', default=3600, cast=int)  # en secondes

# send_confirmation_email
# En dev, mets un backend sûr

# password_reset
# FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173/')
# DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@rio-gold.com')

# SECURE_SSL_REDIRECT = True
# SESSION_COOKIE_SECURE = True
# CSRF_COOKIE_SECURE = True

# --- Proxy/HTTPS (si Nginx) ---
# SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# USE_X_FORWARDED_HOST = True

# --- Sécurité prod (active quand tout est prêt) ---
# SECURE_SSL_REDIRECT = True
# SESSION_COOKIE_SECURE = True
# CSRF_COOKIE_SECURE = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"mailer": {"handlers": ["console"], "level": "INFO", "propagate": False}},
}

# changer le montant minimum du dépôt sans modifier le code source
COMPTE_SOLDE_MINIMUM = 5000  # montant en FCFA
DEPOT_MINIMUM = 5000  # Montant minimal pour un dépôt
RETRAIT_MINIMUM = 5000  # Retrait minimal pour un compte