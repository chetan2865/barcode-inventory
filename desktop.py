"""Barcode Inventory - the desktop application.

Double-clicking the .exe opens the app in its own window. No browser is
launched and no console appears: the window is a native Windows one (Edge
WebView2), and the inventory system runs inside the app itself, served locally
to that window and to nothing else.

What happens on start-up:

1. Django is pointed at the desktop settings - a SQLite database in the user's
   own AppData folder, so the app can write wherever the .exe was copied to.
2. The database is created or brought up to date, and a brand-new installation
   is seeded with the Field Master schema so the forms have their fields.
3. The site is served by waitress on a free local port, bound to 127.0.0.1 so
   nothing outside this machine can reach it.
4. The window opens on the Products page. Closing it quits the app.

If the app window cannot be created (an older machine with no WebView2
runtime), a small Tk window takes over and says what is missing - there is no
console to print to.
"""

import os
import socket
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_desktop")

APP_NAME = "Barcode Inventory"
HOST = "127.0.0.1"
PREFERRED_PORTS = [8000, 8081, 8123, 8756, 9123]
START_PATH = "/inventory/items/"
WINDOW_SIZE = (1440, 900)
MIN_WINDOW_SIZE = (1024, 680)


def _bundle_dir():
    """Where the packaged read-only files sit."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _free_port():
    """First port nothing else is holding - so a second copy still opens."""
    for port in PREFERRED_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if probe.connect_ex((HOST, port)) != 0:
                return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((HOST, 0))
        return probe.getsockname()[1]


def _prepare_database():
    """Create or upgrade the local database, quietly."""
    from django.core.management import call_command

    call_command("migrate", interactive=False, verbosity=0)


def _seed_first_run():
    """Load the shipped Field Master schema, once, into a new installation.

    A migration already plants a small default schema, so "is the table empty"
    is never true - a marker file in the data folder is what tells a genuinely
    first run apart from a laptop that has been in use. That way the fields
    this app was built around arrive on install, and nobody's later edits to
    them are ever overwritten.
    """
    from django.conf import settings
    from django.core.management import call_command

    marker = Path(settings.DATA_ROOT) / ".seeded"
    if marker.exists():
        return

    seed = _bundle_dir() / "seed" / "initial_setup.json"
    if seed.exists():
        call_command("loaddata", str(seed), verbosity=0)
    marker.write_text("ok", encoding="utf-8")


def _collect_static():
    """Put the static assets where WhiteNoise can serve them."""
    from django.conf import settings
    from django.core.management import call_command

    marker = Path(settings.STATIC_ROOT) / ".collected"
    if marker.exists():
        return
    try:
        call_command("collectstatic", interactive=False, verbosity=0, clear=True)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("ok", encoding="utf-8")
    except Exception:
        # Bootstrap is vendored under static/ and WhiteNoise can read it from
        # there, so a failed collect must not stop the app from opening.
        pass


def _start_server(port):
    """Serve the site to this machine only, on a background thread."""
    from waitress import serve

    from config.wsgi import application

    thread = threading.Thread(
        target=serve,
        args=(application,),
        kwargs={"host": HOST, "port": port, "threads": 8, "_quiet": True},
        daemon=True,
    )
    thread.start()
    return thread


def _wait_until_up(port, timeout=25):
    """Block until the server answers, so the window never opens too early."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if probe.connect_ex((HOST, port)) == 0:
                return True
        time.sleep(0.2)
    return False


def _show_error(message):
    """Report a fatal problem in a window - there is no console to print to."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, message)
        root.destroy()
    except Exception:
        pass


def _run_in_app_window(url):
    """The app's own window: native, no browser chrome, no address bar."""
    try:
        import webview
    except ImportError:
        return False

    try:
        webview.create_window(
            APP_NAME,
            url,
            width=WINDOW_SIZE[0],
            height=WINDOW_SIZE[1],
            min_size=MIN_WINDOW_SIZE,
            confirm_close=False,
            text_select=True,
        )
        # Blocks until the user closes the window; that is the app quitting.
        webview.start()
        return True
    except Exception:
        return False


def _run_in_tk_window(url):
    """Fallback when the machine has no WebView2 runtime.

    Rather than dying with no explanation, put up a window of our own saying
    what is missing, with a button to open the app meanwhile.
    """
    import tkinter as tk
    import webbrowser
    from tkinter import ttk

    root = tk.Tk()
    root.title(APP_NAME)
    root.geometry("540x280")
    root.resizable(False, False)

    frame = ttk.Frame(root, padding=24)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text=APP_NAME, font=("Segoe UI", 16, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text=(
            "The app is running, but this machine has no Microsoft Edge\n"
            "WebView2 runtime, which the app window is drawn with.\n\n"
            "Install WebView2 (free, from Microsoft) to get the app window,\n"
            "or open the app in a browser meanwhile."
        ),
        justify="left",
    ).pack(anchor="w", pady=(12, 18))

    buttons = ttk.Frame(frame)
    buttons.pack(anchor="w")
    ttk.Button(buttons, text="Open app", command=lambda: webbrowser.open(url)).pack(side="left")
    ttk.Button(buttons, text="Quit", command=root.destroy).pack(side="left", padx=8)

    root.mainloop()


def main():
    try:
        import django

        django.setup()

        _prepare_database()
        _seed_first_run()
        _collect_static()

        port = _free_port()
        url = f"http://{HOST}:{port}{START_PATH}"

        _start_server(port)
        if not _wait_until_up(port):
            _show_error("The app could not start its local server.\n\nPlease try again.")
            return 1

        if not _run_in_app_window(url):
            _run_in_tk_window(url)
        return 0
    except Exception as error:  # noqa: BLE001 - last resort; the user has no console
        _show_error(f"{APP_NAME} could not start.\n\n{type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
