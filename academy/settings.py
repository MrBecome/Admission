# ================================================================
# DJANGO SETTINGS
# Infinity Academy
# ================================================================

import os
from pathlib import Path

from dotenv import load_dotenv


# ================================================================
# BASE DIRECTORY
# ================================================================

BASE_DIR = Path(__file__).resolve().parent.parent


# ================================================================
# ENVIRONMENT VARIABLES
# ================================================================

ENV_FILE = BASE_DIR / ".env"

if ENV_FILE.exists():
    load_dotenv(
        ENV_FILE,
        override=True,
    )


# ================================================================
# ENVIRONMENT HELPERS
# ================================================================

def env_bool(name, default=False):
    """
    Convert environment values to Python booleans.

    Accepted true values:
        true, 1, yes, y, on
    """
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {
        "true", "1", "yes", "y", "on"
    }


def env_list(name, default=""):
    """
    Read comma-separated environment values.
    """
    value = os.environ.get(name, default)
    return [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ]


# ================================================================
# SECURITY
# ================================================================

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY is missing from .env")


# ================================================================
# DEBUG
# ================================================================
# ✅ Note: In your .env file, set DEBUG=True for local development.
# In production (live server), set DEBUG=False.
DEBUG=False


# ================================================================
# ALLOWED HOSTS
# ================================================================

ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1,13.63.161.216"
)


# ================================================================
# APPLICATIONS
# ================================================================

INSTALLED_APPS = [
    # Django Core
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Infinity Academy
    "admissions",
    "admin_details",
]


# ================================================================
# MIDDLEWARE
# ================================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ================================================================
# URL CONFIGURATION
# ================================================================

ROOT_URLCONF = "academy.urls"
WSGI_APPLICATION = "academy.wsgi.application"


# ================================================================
# TEMPLATES
# ================================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.csrf",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ================================================================
# DATABASE
# ================================================================

DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.mysql"),
        "NAME": os.environ.get("DB_NAME", ""),
        "USER": os.environ.get("DB_USER", ""),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "3306"),
        "OPTIONS": {"charset": "utf8mb4"},
    }
}


# ================================================================
# PASSWORD VALIDATION
# ================================================================

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ================================================================
# INTERNATIONALIZATION
# ================================================================

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = False


# ================================================================
# STATIC & MEDIA FILES
# ================================================================

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ================================================================
# PRIVATE DATA
# ================================================================
PRIVATE_DATA_ROOT = BASE_DIR / "private_data"

# ================================================================
# DEFAULT PRIMARY KEY
# ================================================================
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ================================================================
# EMAIL CONFIGURATION
# ================================================================

EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", default=False)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "").strip()
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")

DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", EMAIL_HOST_USER)
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", ADMIN_EMAIL)


# ================================================================
# OTP CONFIGURATION
# ================================================================

OTP_TOTP_ISSUER = os.environ.get("OTP_TOTP_ISSUER", "Infinity Academy")
OTP_EMAIL_SENDER = os.environ.get("OTP_EMAIL_SENDER", EMAIL_HOST_USER)


# ================================================================
# CSRF & SECURITY CONFIGURATION
# ================================================================

CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", default=False)
CSRF_COOKIE_HTTPONLY = env_bool("CSRF_COOKIE_HTTPONLY", default=False)
CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "Lax")

# ✅ Updated: Ensures local dev URLs are accepted for CSRF
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

SESSION_COOKIE_AGE = int(os.environ.get("SESSION_COOKIE_AGE", "3600"))
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", default=False)
SESSION_COOKIE_HTTPONLY = env_bool("SESSION_COOKIE_HTTPONLY", default=True)
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
SESSION_EXPIRE_AT_BROWSER_CLOSE = env_bool("SESSION_EXPIRE_AT_BROWSER_CLOSE", default=False)


# ================================================================
# HTTPS / SSL / HSTS
# ================================================================

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", default=False)

USE_PROXY_SSL_HEADER = env_bool("USE_PROXY_SSL_HEADER", default=False)
if USE_PROXY_SSL_HEADER:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", default=False)

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = os.environ.get("SECURE_REFERRER_POLICY", "same-origin")


# ================================================================
# MESSAGE FRAMEWORK
# ================================================================

MESSAGE_STORAGE = "django.contrib.messages.storage.fallback.FallbackStorage"


# ================================================================
# FILE UPLOAD LIMITS
# ================================================================

DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get("DATA_UPLOAD_MAX_MEMORY_SIZE", str(10 * 1024 * 1024)))
FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get("FILE_UPLOAD_MAX_MEMORY_SIZE", str(10 * 1024 * 1024)))


# ================================================================
# REDIS / CELERY
# ================================================================

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")