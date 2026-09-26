"""Production settings, used on Railway.

Activated by setting, in the Railway service variables:

    DJANGO_SETTINGS_MODULE = config.settings_production

Everything not restated here is inherited from ``config.settings``, so local
development and the packaged desktop build (``config.settings_desktop``) are
completely unaffected by this file.
"""

import os
import sys

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F401,F403
from .settings import BASE_DIR, MIDDLEWARE

# --------------------------------------------------------------- security --
# No key, no boot: a missing SECRET_KEY must never fall back silently to the
# development value. The one exception is the build step - collectstatic signs
# nothing, and failing the build for a variable it does not use only makes the
# deployment harder to get right.
_secret = os.environ.get("BARCODE_SECRET_KEY")
if not _secret:
    if "collectstatic" in sys.argv:
        _secret = "build-step-placeholder-nothing-is-signed-with-this"
    else:
        raise ImproperlyConfigured(
            "BARCODE_SECRET_KEY is not set. Generate one with: "
            "python -c \"from django.core.management.utils import "
            "get_random_secret_key as k; print(k())\" "
            "and add it to the Railway service variables."
        )
SECRET_KEY = _secret

DEBUG = os.environ.get("DJANGO_DEBUG", "").lower() in {"1", "true", "yes"}

# Railway gives the service a public hostname; allow it plus anything named in
# DJANGO_ALLOWED_HOSTS (comma separated) for a custom domain.
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")
    if host.strip()
]

_railway_host = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
if _railway_host:
    ALLOWED_HOSTS.append(_railway_host)

if not ALLOWED_HOSTS:
    # Railway always sets RAILWAY_PUBLIC_DOMAIN once a domain is generated;
    # before that, refuse rather than open the host header up to anything.
    ALLOWED_HOSTS = [".railway.app"]

# Django 4+ needs the scheme here, not just the host.
CSRF_TRUSTED_ORIGINS = [
    f"https://{host.lstrip('.')}" if not host.startswith("http") else host
    for host in ALLOWED_HOSTS
]
CSRF_TRUSTED_ORIGINS.append("https://*.railway.app")

# Railway terminates TLS at its edge and forwards the original scheme here.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "1") != "0"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = bool(SECURE_HSTS_SECONDS)
SECURE_HSTS_PRELOAD = bool(SECURE_HSTS_SECONDS)
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

# -------------------------------------------------------------- database --
# Railway injects DATABASE_URL when a Postgres service is attached. Without
# one this falls back to SQLite, which on Railway lives on an ephemeral disk -
# fine for a first smoke test, wrong for anything real.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=False,
    )
}

# ---------------------------------------------------------- static files --
# WhiteNoise serves the collected static files straight from the web process,
# so no separate CDN or storage bucket is needed.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *[m for m in MIDDLEWARE if m != "django.middleware.security.SecurityMiddleware"],
]

STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        # Hashed, compressed filenames with a manifest. "NonStrict" so a
        # missing reference logs instead of taking the whole page down.
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
WHITENOISE_MANIFEST_STRICT = False

# ----------------------------------------------------------- media files --
# IMPORTANT: this application WRITES to MEDIA_ROOT at runtime - every entry's
# barcode PNG, plus uploaded signatures, logos and payment QR codes. Railway's
# container filesystem is wiped on every deploy and restart, so MEDIA_ROOT must
# point at an attached Railway Volume or those images disappear.
#
# Attach a Volume to the service; Railway then sets RAILWAY_VOLUME_MOUNT_PATH.
_volume = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
_media_parent = _volume if _volume else str(BASE_DIR)
MEDIA_ROOT = os.path.join(_media_parent, "media")
MEDIA_URL = "/media/"

# config/urls.py only wires up /media/ when DEBUG is on, so in production
# WhiteNoise serves it instead: it exposes everything under WHITENOISE_ROOT at
# the URL root, and MEDIA_ROOT is <parent>/media, so a barcode at
# <parent>/media/barcodes/x.png is served at /media/barcodes/x.png.
WHITENOISE_ROOT = _media_parent

# Barcode PNGs are written *while the server runs*. Without autorefresh
# WhiteNoise only indexes files present at boot, and every barcode generated
# after startup would 404 until the next deploy.
WHITENOISE_AUTOREFRESH = True

# ---------------------------------------------------------------- logging --
# Straight to stdout, which is what Railway's log viewer reads.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}
