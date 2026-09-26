"""Settings for the packaged desktop app.

The web project is unchanged - same pages, same tables, same logic. What
differs is where things live and who is allowed in:

* the database and uploaded media sit in the user's own AppData folder, so the
  app can write to them wherever the .exe was copied to (Program Files, a USB
  stick, another laptop);
* static files are served by WhiteNoise instead of the dev server;
* the Django admin is not routed at all - the front-end pages are the whole
  application as far as the end user is concerned.
"""

import os
import sys
from pathlib import Path

from .settings import *  # noqa: F401,F403

# Marks this as the packaged build. config/urls.py reads it to leave the admin
# out, and the templates read it to hide anything staff-only.
DESKTOP_APP = True

DEBUG = False
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]


def _bundle_root():
    """Where the read-only application files live.

    PyInstaller unpacks them into a temp folder it points ``sys._MEIPASS`` at;
    running from source it is just the project directory.
    """
    bundled = getattr(sys, "_MEIPASS", None)
    return Path(bundled) if bundled else Path(__file__).resolve().parent.parent


def _data_root():
    """Where this installation keeps its own data - writable, and it persists.

    Deliberately not next to the .exe: that may be read-only, and a copy of the
    program should never carry someone else's stock around with it.
    """
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = Path(base) / "BarcodeInventory"
    path.mkdir(parents=True, exist_ok=True)
    return path


BUNDLE_ROOT = _bundle_root()
DATA_ROOT = _data_root()

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(DATA_ROOT / "db.sqlite3"),
    }
}

MEDIA_ROOT = str(DATA_ROOT / "media")
MEDIA_URL = "/media/"

STATIC_URL = "/static/"
STATIC_ROOT = str(DATA_ROOT / "static")

# WhiteNoise serves both the collected static files and, through the extra
# directory below, the barcode PNGs this app generates at runtime.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *[m for m in MIDDLEWARE if m != "django.middleware.security.SecurityMiddleware"],  # noqa: F405
]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

WHITENOISE_AUTOREFRESH = True

# A single local user on their own machine - no cross-site risk to guard, and
# nothing to gain from forcing HTTPS on 127.0.0.1.
SECRET_KEY = os.environ.get("BARCODE_SECRET_KEY", SECRET_KEY)  # noqa: F405
CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1", "http://localhost"]
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
