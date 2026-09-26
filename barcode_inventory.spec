# PyInstaller build for the Barcode Inventory desktop app.
#
#   pyinstaller barcode_inventory.spec --noconfirm
#
# Produces dist/BarcodeInventory/BarcodeInventory.exe - a folder you can zip
# and hand to another laptop. Nothing needs installing there: no Python, no
# Django, no database server.
#
# Templates, migrations and the barcode font are data, not code, so PyInstaller
# cannot find them by following imports - they are listed explicitly below.

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

project = Path(SPECPATH)

datas = [
    (str(project / "items" / "templates"), "items/templates"),
    (str(project / "static"), "static"),
    (str(project / "seed"), "seed"),
    (str(project / "field_master" / "templates"), "field_master/templates"),
    # The invoicing screens were never bundled - they 500 in the packaged
    # build without this.
    (str(project / "invoicing" / "templates"), "invoicing/templates"),
    # The shared application shell (templates/base.html) lives at project level.
    (str(project / "templates"), "templates"),
    (str(project / "items" / "migrations"), "items/migrations"),
    (str(project / "field_master" / "migrations"), "field_master/migrations"),
]

# The DejaVu font python-barcode prints the human-readable value with.
datas += collect_data_files("barcode")

binaries = []

hiddenimports = [
    "config.settings",
    "config.settings_desktop",
    "config.wsgi",
    # INSTALLED_APPS names these as strings, so nothing imports them.
    "config.apps",
    "config.admin",
    "waitress",
    "whitenoise",
    "whitenoise.storage",
    "whitenoise.middleware",
    # Django loads these by name at runtime, so nothing imports them directly.
    "django.contrib.admin.apps",
    "django.contrib.auth.apps",
    "django.contrib.contenttypes.apps",
    "django.contrib.sessions.apps",
    "django.contrib.messages.apps",
    "django.contrib.staticfiles.apps",
    "django.db.backends.sqlite3",
    "django.template.loaders.filesystem",
    "django.template.loaders.app_directories",
]
hiddenimports += collect_submodules("config")
hiddenimports += collect_submodules("items")
hiddenimports += collect_submodules("field_master")
hiddenimports += collect_submodules("core")
hiddenimports += collect_submodules("barcode")

# The app window: pywebview draws it with Edge WebView2 through pythonnet, all
# of which is loaded dynamically at runtime, so it has to be collected whole.
for package in ("webview", "clr_loader", "pythonnet"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

hiddenimports += [
    "webview.platforms.edgechromium",
    "clr_loader",
    "tkinter",
    "tkinter.ttk",
    "tkinter.messagebox",
]

a = Analysis(
    ["desktop.py"],
    pathex=[str(project)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # psycopg2 is only there for the server deployment; the desktop build is
    # SQLite, and pulling in Postgres bindings would just bloat it.
    excludes=["psycopg2", "psycopg2-binary", "test", "unittest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BarcodeInventory",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,         # a desktop app, not a terminal program
    disable_windowed_traceback=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BarcodeInventory",
)
