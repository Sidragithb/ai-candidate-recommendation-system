import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "DJANGO_ALLOWED_HOSTS",
        "127.0.0.1,localhost,testserver",
    ).split(",")
    if host.strip()
]
for default_host in [".ngrok-free.dev", ".ngrok.app", ".ngrok.dev"]:
    if default_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(default_host)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.jobs",
    "apps.candidates",
    "apps.chatbot",
    "apps.vapi",
    "apps.ai",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "candidate_ai.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "candidate_ai.wsgi.application"
ASGI_APPLICATION = "candidate_ai.asgi.application"

DB_ENGINE = os.getenv("DJANGO_DB_ENGINE", "sqlite").lower()

if DB_ENGINE == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DJANGO_DB_NAME", "candidate_ai"),
            "USER": os.getenv("DJANGO_DB_USER", "postgres"),
            "PASSWORD": os.getenv("DJANGO_DB_PASSWORD", "postgres"),
            "HOST": os.getenv("DJANGO_DB_HOST", "localhost"),
            "PORT": os.getenv("DJANGO_DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / os.getenv("DJANGO_SQLITE_NAME", "db.sqlite3"),
        }
    }

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / os.getenv("DJANGO_MEDIA_ROOT", "media")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "false").lower() == "true"
SESSION_COOKIE_SECURE = os.getenv("DJANGO_SESSION_COOKIE_SECURE", "false").lower() == "true"
CSRF_COOKIE_SECURE = os.getenv("DJANGO_CSRF_COOKIE_SECURE", "false").lower() == "true"
if os.getenv("DJANGO_USE_X_FORWARDED_PROTO", "false").lower() == "true":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

QDRANT_URL = os.getenv("QDRANT_URL", os.getenv("APP_QDRANT_URL", "http://localhost:6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", os.getenv("APP_QDRANT_COLLECTION", "candidate_embeddings"))
EMBEDDING_VECTOR_SIZE = int(
    os.getenv("EMBEDDING_VECTOR_SIZE", os.getenv("APP_EMBEDDING_VECTOR_SIZE", "3"))
)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", os.getenv("APP_EMBEDDING_MODEL", "gpt-5-mini"))
EMBEDDING_PROVIDER = os.getenv(
    "EMBEDDING_PROVIDER", os.getenv("APP_EMBEDDING_PROVIDER", "placeholder")
)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
ASSISTANT_MODEL = os.getenv("ASSISTANT_MODEL", "gpt-5-mini")
ASSISTANT_PROVIDER = os.getenv("ASSISTANT_PROVIDER", "placeholder")
VAPI_ASSISTANT_NAME = os.getenv("VAPI_ASSISTANT_NAME", "Hiring Assistant")
VAPI_VOICE_PROVIDER = os.getenv("VAPI_VOICE_PROVIDER", "openai")
VAPI_VOICE_ID = os.getenv("VAPI_VOICE_ID", "alloy")
VAPI_FIRST_MESSAGE = os.getenv(
    "VAPI_FIRST_MESSAGE",
    "Good day. This is Ava, your AI hiring assistant. How can I help you review candidates today?",
)
