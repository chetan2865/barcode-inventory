from django.apps import AppConfig


class ItemsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'items'

    def ready(self):
        # On the server this stays off on purpose - barcodes are minted in
        # batches with `manage.py generate_barcodes`, and signals.py holds the
        # sync-on-save logic ready.
        #
        # The packaged desktop app has no command line, so an entry saved there
        # would have no barcode row and its label would not scan. There, the
        # signal is wired up and every entry gets its barcode as it is saved.
        from django.conf import settings

        if getattr(settings, "DESKTOP_APP", False):
            from . import signals  # noqa: F401
