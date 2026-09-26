"""Backfill/re-sync barcodes so every Sku has one whose value == its SKU code.

Legacy barcodes encoded ``<object_type>|<pk>`` (e.g. ``01|5``) with no visible
text. This regenerates each Sku's barcode image from the SKU code itself, and
creates a barcode for any Sku that never had one. Idempotent and safe to re-run.
"""

from django.db import migrations


def resync_barcodes(apps, schema_editor):
    from items import barcode as barcode_engine
    from core.object_types import SKU as OBJECT_TYPE_SKU

    Sku = apps.get_model("items", "Sku")
    Barcode = apps.get_model("items", "Barcode")

    for sku in Sku.objects.all():
        filename, content = barcode_engine.generate_image(sku.code)
        barcode = Barcode.objects.filter(sku_id=sku.pk).first()
        if barcode is None:
            barcode = Barcode(sku_id=sku.pk, object_type=OBJECT_TYPE_SKU, object_id=sku.pk)
        barcode.value = sku.code
        barcode.object_id = sku.pk
        barcode.image.save(filename, content, save=False)
        barcode.save()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('items', '0004_skuformat_alter_barcode_value_alter_sku_code'),
    ]

    operations = [
        migrations.RunPython(resync_barcodes, noop),
    ]
