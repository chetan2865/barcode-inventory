"""Builds ONE field JSON object from submitted form data.

Every field the administrator creates becomes exactly one JSON object that
owns its own ``configuration``. The configuration keys depend on the field
``type``. This module is the single place that knows that mapping.
"""

# Allowed field types (value -> label shown in the UI).
FIELD_TYPES = [
    ("text", "Text"),
    ("number", "Number"),
    ("date", "Date"),
    ("file", "File"),
    ("long_text", "Long Text"),
    ("boolean", "True / False"),
    ("dropdown", "Dropdown"),
]

# Allowed field sizes.
FIELD_SIZES = ["S", "M", "L", "XL", "XXL"]

# How a value is reduced to its SKU component (per-field override; blank = use
# the global SkuFormat default).
SKU_TRANSFORMS = [
    ("", "Default (global)"),
    ("alpha", "Letters only"),
    ("alnum", "Letters + digits"),
    ("digits", "Digits only"),
    ("full", "Keep as-is (alnum)"),
]


def _to_int(value):
    """Return an int for a filled-in value, or None when left blank."""
    if value is None:
        return None
    value = str(value).strip()
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _clean_str(value):
    """Return a stripped string, or None when blank."""
    if value is None:
        return None
    value = str(value).strip()
    return value if value != "" else None


def build_configuration(field_type, data):
    """Build the type-specific ``configuration`` object from form ``data``.

    ``data`` is a request.POST-like mapping.
    """
    if field_type == "dropdown":
        # Options come in as one option per line in a textarea.
        raw = data.get("options", "") or ""
        options = [line.strip() for line in raw.splitlines() if line.strip()]
        return {"options": options}

    if field_type == "text":
        return {
            "placeholder": _clean_str(data.get("placeholder")),
            "max_length": _to_int(data.get("max_length")),
        }

    if field_type == "number":
        return {
            "minimum": _to_int(data.get("minimum")),
            "maximum": _to_int(data.get("maximum")),
            "decimal_places": _to_int(data.get("decimal_places")),
        }

    if field_type == "date":
        return {
            "minimum_date": _clean_str(data.get("minimum_date")),
            "maximum_date": _clean_str(data.get("maximum_date")),
        }

    if field_type == "file":
        raw = data.get("allowed_extensions", "") or ""
        extensions = [ext.strip() for ext in raw.split(",") if ext.strip()]
        return {
            "allowed_extensions": extensions,
            "maximum_file_size": _to_int(data.get("maximum_file_size")),
        }

    if field_type == "long_text":
        return {
            "rows": _to_int(data.get("rows")),
            "max_length": _to_int(data.get("max_length")),
        }

    if field_type == "boolean":
        return {
            "default_value": data.get("default_value") == "on",
        }

    return {}


def build_sku_config(data):
    """Per-field SKU overrides. Blank values mean "use the global default".

    Kept out of ``configuration`` (which is type-specific) because these apply
    to how the field participates in SKU composition, regardless of its type.
    Uppercase is NOT overridable here - every SKU is always uppercase, a
    fixed rule enforced in ``items.sku``, not a per-field preference.
    """
    transform = _clean_str(data.get("sku_transform"))
    if transform not in {t[0] for t in SKU_TRANSFORMS if t[0]}:
        transform = None
    return {
        "order": _to_int(data.get("sku_order")),
        "length": _to_int(data.get("sku_length")),
        "transform": transform,
    }


def build_field(data):
    """Build ONE complete field JSON object from form ``data``.

    Fields built here are always user-defined (``system: False``). System
    fields (Product Name, HSN, ...) are seeded once via a data migration and
    are never created through this form.
    """
    field_type = data.get("type", "text")
    include_in_sku = data.get("include_in_sku") == "on"
    mandatory = data.get("mandatory") == "on"
    return {
        "name": _clean_str(data.get("name")) or "",
        "type": field_type,
        "include_in_sku": include_in_sku,
        "include_in_invoice_description": data.get("include_in_invoice_description") == "on",
        "mandatory": mandatory,
        # Mandatory fields must always stay visible.
        "hide": False if mandatory else data.get("hide") == "on",
        "field_size": data.get("field_size", "M"),
        "configuration": build_configuration(field_type, data),
        "sku_config": build_sku_config(data) if include_in_sku else {},
        "system": False,
    }
