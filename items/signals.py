from django.db.models.signals import post_save
from django.dispatch import receiver

from . import barcode as barcode_engine
from .models import Item


@receiver(post_save, sender=Item)
def sync_barcode_on_entry_save(sender, instance, created, **kwargs):
    """Keep each entry's Barcode in step: create on first save, resync on change."""
    if created:
        barcode_engine.create_barcode_for_entry(instance)
    else:
        barcode_engine.sync_barcode_for_entry(instance)
