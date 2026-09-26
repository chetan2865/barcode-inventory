"""Give every existing Item row an Entry to hang off.

Rows created before the Entry table have no grouping, which would leave them
invisible on a display that walks product -> entry -> SKU. Lines saved in the
same second with the same product data almost certainly came from one save, so
they are grouped together; everything else becomes an entry of its own.

Display only - no quantity, code or barcode is touched.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    Entry = apps.get_model("items", "Entry")
    Item = apps.get_model("items", "Item")

    groups = {}
    for item in Item.objects.filter(entry__isnull=True).order_by("pk"):
        key = (
            item.data.get("Product Name") or "",
            item.created_at.replace(microsecond=0),
        )
        groups.setdefault(key, []).append(item)

    for (product, _), lines in groups.items():
        entry = Entry.objects.create(
            product=product,
            data=dict(lines[0].data),
            created_at=lines[0].created_at,
        )
        for line in lines:
            line.entry = entry
            line.save(update_fields=["entry"])


def unlink(apps, schema_editor):
    Item = apps.get_model("items", "Item")
    Item.objects.update(entry=None)
    apps.get_model("items", "Entry").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("items", "0010_entry_item_entry"),
    ]

    operations = [
        migrations.RunPython(backfill, unlink),
    ]
