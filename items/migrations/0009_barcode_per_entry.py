"""Barcodes move from the SKU to the entry.

Each intake carries its own label, so the Barcode row hangs off Item instead
of Sku. There are no barcode rows at this point (the SKU-level ones were
cleared with the old data), so the old field is simply dropped and the new one
added; `manage.py generate_barcodes` mints the entry labels.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("items", "0008_remove_sku_items_item_sku"),
    ]

    operations = [
        migrations.RunSQL("DELETE FROM items_barcode;", migrations.RunSQL.noop),
        migrations.RemoveField(model_name="barcode", name="sku"),
        migrations.AddField(
            model_name="barcode",
            name="entry",
            field=models.OneToOneField(
                default=None,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="barcode",
                to="items.item",
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="barcode",
            name="entry",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="barcode",
                to="items.item",
            ),
        ),
        migrations.AlterField(
            model_name="barcode",
            name="object_type",
            field=models.CharField(
                choices=[
                    ("01", "SKU"), ("02", "Item"), ("03", "Vendor"), ("04", "Customer"),
                    ("05", "Warehouse"), ("06", "Purchase"), ("07", "Sales"),
                    ("08", "BOM"), ("09", "Stock"), ("10", "Barcode"),
                ],
                default="02",
                max_length=2,
            ),
        ),
    ]
