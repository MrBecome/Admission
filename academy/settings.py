import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-fallback-key')
DEBUG = os.environ.get('DEBUG', 'True') == 'True'
# Read allowed hosts from comma-separated .env value, fallback to localhost
_allowed = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1')
ALLOWED_HOSTS = [h.strip() for h in _allowed.split(',') if h.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'admissions',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'academy.urls'
WSGI_APPLICATION = 'academy.wsgi.application'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'

# CRITICAL: registrar's office operates on Indian Standard Time - admission
# dates, payment timestamps, and OTP expiry windows must all read correctly
# in IST, not UTC.
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = False

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('DB_NAME'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST'),
        'PORT': os.environ.get('DB_PORT'),
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.csrf',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CRITICAL: this folder holds admin-uploaded source spreadsheets (courses.xlsx)
# and must NEVER be reachable over HTTP. It is deliberately its own root,
# NOT a subfolder of STATICFILES_DIRS or MEDIA_ROOT above - both of those are
# served directly to the public (via collectstatic / the /media/ URL), and
# anything placed under them becomes downloadable by anyone who guesses the
# path. Only server-side code (the course importer, the admin uploader view)
# should ever touch PRIVATE_DATA_ROOT.
PRIVATE_DATA_ROOT = BASE_DIR / 'private_data'

# Email and cookie settings (read from environment with sensible defaults)
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', f'Infinity Academy <{EMAIL_HOST_USER}>')
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', EMAIL_HOST_USER)

# CSRF / Session cookie security flags (configurable via .env)
CSRF_COOKIE_SECURE = os.environ.get('CSRF_COOKIE_SECURE', 'False') == 'True'
SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False') == 'True'
SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'False') == 'True'

# Optional trusted origins (comma-separated) for deployments behind proxies
_csrf_trusted = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
if _csrf_trusted:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_trusted.split(',') if o.strip()]
else:
    CSRF_TRUSTED_ORIGINS = []

# ========================
# CSRF & Security Fixes
# ========================
# Allow the CSRF token to work over HTTP for local testing
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

# Allow localhost and 127.0.0.1 to bypass CSRF checks (Vital for local development)
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]