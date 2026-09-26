from django.db import migrations

PAGE_NAME = "Item Registration"

# Mirrors 0002_seed_system_fields.SYSTEM_FIELDS. Duplicated here (rather than
# imported, since migration modules start with digits and aren't importable
# by name) so this migration stays self-contained.
SYSTEM_FIELDS = [
    {
        "name": "Product Name",
        "type": "text",
        "include_in_sku": False,
        "include_in_invoice_description": True,
        "mandatory": True,
        "hide": False,
        "field_size": "L",
        "configuration": {"placeholder": None, "max_length": None},
        "sku_config": {},
        "system": True,
    },
    {
        "name": "HSN",
        "type": "text",
        "include_in_sku": False,
        "include_in_invoice_description": False,
        "mandatory": True,
        "hide": False,
        "field_size": "M",
        "configuration": {"placeholder": None, "max_length": None},
        "sku_config": {},
        "system": True,
    },
    {
        "name": "Cost Rate",
        "type": "number",
        "include_in_sku": False,
        "include_in_invoice_description": False,
        "mandatory": True,
        "hide": False,
        "field_size": "M",
        "configuration": {"minimum": 0, "maximum": None, "decimal_places": 2},
        "sku_config": {},
        "system": True,
    },
    {
        "name": "Rate",
        "type": "number",
        "include_in_sku": False,
        "include_in_invoice_description": False,
        "mandatory": True,
        "hide": False,
        "field_size": "M",
        "configuration": {"minimum": 0, "maximum": None, "decimal_places": 2},
        "sku_config": {},
        "system": True,
    },
    {
        "name": "Manufacturing Cost",
        "type": "number",
        "include_in_sku": False,
        "include_in_invoice_description": False,
        "mandatory": True,
        "hide": False,
        "field_size": "M",
        "configuration": {"minimum": 0, "maximum": None, "decimal_places": 2},
        "sku_config": {},
        "system": True,
    },
    {
        "name": "GST Rate",
        "type": "number",
        "include_in_sku": False,
        "include_in_invoice_description": False,
        "mandatory": True,
        "hide": False,
        "field_size": "M",
        "configuration": {"minimum": 0, "maximum": 100, "decimal_places": 2},
        "sku_config": {},
        "system": True,
    },
]


def fix_system_fields(apps, schema_editor):
    """0002 skipped seeding any system field whose name already collided with
    a pre-existing, non-system field (e.g. a "Product Name" field created by
    hand before this migration existed). Upgrade those in place instead of
    leaving them as ordinary, editable/deletable fields.
    """
    MasterSchema = apps.get_model("field_master", "MasterSchema")
    schema, _ = MasterSchema.objects.get_or_create(page=PAGE_NAME)

    fields = list(schema.fields)
    by_name = {f.get("name"): i for i, f in enumerate(fields)}

    for system_field in SYSTEM_FIELDS:
        name = system_field["name"]
        if name in by_name:
            fields[by_name[name]] = dict(system_field)
        else:
            fields.insert(0, dict(system_field))

    system_names = [f["name"] for f in SYSTEM_FIELDS]
    fields.sort(key=lambda f: system_names.index(f["name"]) if f.get("name") in system_names else len(system_names))
    schema.fields = fields
    schema.save()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("field_master", "0002_seed_system_fields"),
    ]

    operations = [
        migrations.RunPython(fix_system_fields, noop),
    ]
