from django.db import migrations

PAGE_NAME = "Item Registration"

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


def seed_system_fields(apps, schema_editor):
    MasterSchema = apps.get_model("field_master", "MasterSchema")
    schema, _ = MasterSchema.objects.get_or_create(page=PAGE_NAME)

    existing_names = {f.get("name") for f in schema.fields}
    fields = list(schema.fields)
    for field in SYSTEM_FIELDS:
        if field["name"] not in existing_names:
            fields.insert(0, field)
    # Keep system fields at the front, in the order declared above.
    system_names = [f["name"] for f in SYSTEM_FIELDS]
    fields.sort(key=lambda f: system_names.index(f["name"]) if f.get("name") in system_names else len(system_names))
    schema.fields = fields
    schema.save()


def unseed_system_fields(apps, schema_editor):
    MasterSchema = apps.get_model("field_master", "MasterSchema")
    try:
        schema = MasterSchema.objects.get(page=PAGE_NAME)
    except MasterSchema.DoesNotExist:
        return
    system_names = {f["name"] for f in SYSTEM_FIELDS}
    schema.fields = [f for f in schema.fields if f.get("name") not in system_names]
    schema.save()


class Migration(migrations.Migration):

    dependencies = [
        ("field_master", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_system_fields, unseed_system_fields),
    ]
