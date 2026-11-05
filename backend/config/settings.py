import os
from pathlib import Path

from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
MFA_ENCRYPTION_KEY = os.environ["MFA_ENCRYPTION_KEY"]
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must contain at least 50 characters")
try:
    Fernet(MFA_ENCRYPTION_KEY.encode())
except (ValueError, TypeError) as exc:
    raise ImproperlyConfigured("MFA_ENCRYPTION_KEY must be a Fernet key") from exc
DEBUG = os.getenv("DJANGO_DEBUG", "false") == "true"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
PUBLIC_ORIGIN = os.getenv("PUBLIC_ORIGIN", "http://localhost:8080")
CSRF_TRUSTED_ORIGINS = [PUBLIC_ORIGIN]
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rest_framework",
    "drf_spectacular",
    "identity",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "identity.security.SecurityMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "health"),
        "USER": os.getenv("POSTGRES_USER", "health"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}
AUTH_USER_MODEL = "identity.User"
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]
LANGUAGE_CODE = "it"
LANGUAGES = [("it", "Italiano"), ("en", "English")]
TIME_ZONE = "Europe/Rome"
USE_TZ = True
USE_I18N = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 3600
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_REFERRER_POLICY = "same-origin"
DATA_UPLOAD_MAX_MEMORY_SIZE = 65536
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "mail")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "1025"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "false") == "true"
EMAIL_TIMEOUT = 10
EMAIL_FILE_PATH = os.getenv("EMAIL_FILE_PATH", str(BASE_DIR / ".test-mail"))
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@health.example")
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["identity.security.StrictSessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["identity.security.Ready"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "EXCEPTION_HANDLER": "identity.security.exception_handler",
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Health collaboration — M2",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "ProfileRoleEnum": ["patient", "professional", "researcher", "organization_admin"],
        "MembershipRoleEnum": ["admin", "professional", "researcher"],
        "LocaleEnum": ["it", "en"],
        "DecisionEnum": ["granted", "revoked"],
        "AnalysisDecisionEnum": ["accept", "modify", "reject"],
    },
}
CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_IGNORE_RESULT = True
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CLINICAL_MASTER_KEY = os.environ.get("CLINICAL_MASTER_KEY", "")

CELERY_BEAT_SCHEDULE = {
    "clinical-storage-reconciliation": {
        "task": "identity.tasks.reconcile_clinical_storage",
        "schedule": 60.0,
    },
}

CLINICAL_ANALYSIS_ENABLED = os.getenv("CLINICAL_ANALYSIS_ENABLED", "") == "1"
CELERY_TASK_ROUTES = {
    "identity.tasks.run_clinical_analysis": {"queue": "clinical-analysis"},
    "identity.tasks.reconcile_analysis_jobs": {"queue": "clinical-analysis"},
}
CELERY_BEAT_SCHEDULE["clinical-analysis-reconciliation"] = {
    "task": "identity.tasks.reconcile_analysis_jobs",
    "schedule": 15.0,
}
