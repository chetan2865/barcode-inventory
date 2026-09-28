"""Dynamic form helpers driven entirely by the field_master Master JSON.

No field is hardcoded here: every input, its validation and its stored
value are derived from a field's ``type``, ``mandatory``, ``hide`` and
``configuration`` properties as defined in the Master JSON.
"""

from django.core.files.storage import default_storage

# Bootstrap column width for each Master JSON "field_size".
SIZE_COLUMNS = {
    "S": "col-md-2",
    "M": "col-md-4",
    "L": "col-md-6",
    "XL": "col-md-8",
    "XXL": "col-md-12",
}


def visible_fields(schema_fields):
    """Fields that should appear on the Item Registration form/table."""
    return [f for f in schema_fields if not f.get("hide")]


def registration_schema(schema_fields):
    """Schema fields as Item Registration/Display must see them.

    Fields marked "Include in SKU" belong to SKU Creation only: their values
    are never entered or shown on the Item side. Reusing the existing
    ``hide`` handling (never rendered, never required, never written to
    Item.data) keeps that guarantee without touching the SKU Creation code
    path, which needs those same fields fully visible.

    Quantity rides along on the SKU Creation form too, but it is stock rather
    than identity: it is stored per SKU inside the item's own JSON (see
    items.quantity) and never reaches Sku.data or a code.
    """
    from .sku import is_size_field

    return [
        {**field, "hide": True}
        if field.get("include_in_sku") or is_size_field(field)
        else field
        for field in schema_fields
    ]


def column_class(field):
    return SIZE_COLUMNS.get(field.get("field_size"), "col-md-4")


def input_name(index):
    """The HTML ``name`` used for the field at ``index`` in schema order."""
    return f"field_{index}"


def parse_item_data(schema_fields, post, files, existing_data=None):
    """Build the ``data`` dict (field name -> value) from a submitted form.

    Returns ``(data, errors)``. ``existing_data`` supplies fallback values
    for fields left blank on edit (e.g. a file that wasn't re-uploaded).
    """
    existing_data = existing_data or {}
    data = {}
    errors = []

    for index, field in enumerate(schema_fields):
        if field.get("hide"):
            data[field["name"]] = existing_data.get(field["name"])
            continue

        name = input_name(index)
        field_type = field.get("type")
        label = field["name"]

        if field_type == "boolean":
            data[label] = post.get(name) == "on"
            continue

        if field_type == "file":
            uploaded = files.get(name)
            if uploaded:
                path = default_storage.save(f"items/{uploaded.name}", uploaded)
                data[label] = default_storage.url(path)
            else:
                data[label] = existing_data.get(label, "")
            if field.get("mandatory") and not data[label]:
                errors.append(f'"{label}" is required.')
            continue

        value = (post.get(name) or "").strip()
        if field.get("mandatory") and value == "":
            errors.append(f'"{label}" is required.')
        data[label] = value

    return data, errors
