from django.db.models.signals import post_save
from django.dispatch import receiver

from . import barcode as barcode_engine
from .models import Item


@receiver(post_save, sender=Item)
def sync_barcode_on_entry_save(sender, instance, created, raw=False, **kwargs):
    """Keep each entry's Barcode in step: create on first save, resync on change.

    ``raw`` is set while a fixture is being loaded. Those rows carry their own
    Barcode records and the SKU they point at may not be in the database yet,
    so minting one here would either duplicate or fail - loaddata is left to
    install the barcodes the fixture already holds.
    """
    if raw:
        return

    if created:
        barcode_engine.create_barcode_for_entry(instance)
    else:
        barcode_engine.sync_barcode_for_entry(instance)
