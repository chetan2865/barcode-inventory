from django.apps import AppConfig


class ItemsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'items'

    def ready(self):
        # Every entry gets its barcode as it is saved, everywhere.
        #
        # This used to be wired up only for the packaged desktop app, on the
        # reasoning that a server has a command line and can mint barcodes in
        # batches with `manage.py generate_barcodes`. That left anything added
        # through the web UI with no barcode row - nothing to scan, and no
        # label to print - until someone remembered to run the command. A
        # hosted deployment has no convenient command line either, so the
        # desktop's reasoning now applies everywhere.
        #
        # `generate_barcodes` still exists and is still the way to repair or
        # backfill in bulk; it is simply no longer the only way one appears.
        from . import signals  # noqa: F401
