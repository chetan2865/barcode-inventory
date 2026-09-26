"""Load the starting catalogue, but only into a database that has none.

Runs on every deploy, straight after `migrate`. A freshly migrated database
has only the system fields the migrations create - Product Name, HSN, Cost
Rate, Rate, Manufacturing Cost, GST Rate - and no stock at all, so the app
comes up with a schema nobody asked for and an empty Products page.

This fills that in once. The moment there is any real inventory it does
nothing, so a deploy can never overwrite stock that has been entered through
the UI.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand

from items.models import Item

FIXTURE = "seed/catalogue.json"


class Command(BaseCommand):
    help = "Seed the starting catalogue into an empty database (no-op otherwise)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Load the fixture even if inventory already exists (overwrites by pk).",
        )

    def handle(self, *args, **options):
        existing = Item.objects.count()

        if existing and not options["force"]:
            self.stdout.write(
                f"Inventory already present ({existing} items) - leaving it alone."
            )
            return

        call_command("loaddata", FIXTURE, verbosity=0)
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded starting catalogue: {Item.objects.count()} items."
            )
        )
