"""Backfill Barcode records for every entry.

Barcodes are per entry: each intake carries its own label, so two lots of the
same variant can be told apart on the shelf. Barcode auto-generation on save is
deliberately unwired (see items.apps), so entries created through the UI have no
Barcode row. This command brings every entry up to date in one pass: it creates
missing barcodes, regenerates ones whose value drifted, and re-renders images
whose file is gone from media/.
"""

import os

from django.core.management.base import BaseCommand

from items import barcode as barcode_engine
from items.models import Item


class Command(BaseCommand):
    help = "Generate (or repair) the Code128 barcode for every entry."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-render every barcode image, even ones already correct.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        force = options["force"]
        dry_run = options["dry_run"]

        created = resynced = rerendered = unchanged = 0

        skipped = 0
        for entry in Item.objects.select_related("barcode", "sku").order_by("pk"):
            value = barcode_engine.build_value(entry)
            if value is None:  # entry has no SKU yet - nothing to encode
                skipped += 1
                continue

            existing = getattr(entry, "barcode", None)

            if existing is None:
                action, style = "create", self.style.SUCCESS
                created += 1
            elif existing.value != value:
                action, style = "resync", self.style.WARNING
                resynced += 1
            elif force or not self._image_present(existing):
                action, style = "re-render", self.style.WARNING
                rerendered += 1
            else:
                unchanged += 1
                continue

            if not dry_run:
                if action == "re-render":
                    filename, content = barcode_engine.generate_image(value)
                    existing.image.save(filename, content, save=False)
                    existing.save()
                else:
                    barcode_engine.sync_barcode_for_entry(entry)

            self.stdout.write(style(f"  {action:<10} #{entry.pk} {value}"))

        summary = (
            f"created {created}, resynced {resynced}, re-rendered {rerendered}, "
            f"unchanged {unchanged}, skipped (no SKU) {skipped}"
        )
        if dry_run:
            self.stdout.write(self.style.NOTICE(f"Dry run - nothing written. Would be: {summary}."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Done: {summary}."))

    @staticmethod
    def _image_present(record):
        """True when the barcode's PNG still exists on disk."""
        if not record.image:
            return False
        try:
            return os.path.exists(record.image.path)
        except (NotImplementedError, ValueError):
            # Non-filesystem storage backends: trust the record.
            return True
