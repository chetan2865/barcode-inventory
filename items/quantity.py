"""Entry-level quantity.

One entry is one row in the Products table: product data + one SKU + the
quantity that entry was taken in with. Quantity is an ordinary Master JSON
field inside ``Item.data``, so it rides along in the entry's own JSON::

    {"id": 21, "Product Name": "T-Shirt", "Manufacturing Cost": 410,
     "sku": "COT-HAL-BLA-002", "Quantity": 75}

Quantities of separate entries are never added together: taking the same
variant in again creates another entry with its own number, and both entries
stand on their own in the Products table.
"""

from .sku import quantity_fields


def to_number(value):
    """Best-effort numeric read of a quantity value.

    Values arrive from a JSON field and may be ``12``, ``"12"``, ``"12 pcs"``
    or blank, so anything unreadable counts as zero rather than raising.
    """
    if value is None or value == "" or isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return value

    digits = "".join(ch for ch in str(value) if ch.isdigit() or ch == ".")
    if not digits or digits == ".":
        return 0
    try:
        number = float(digits)
    except ValueError:
        return 0
    return int(number) if number.is_integer() else number


def quantity_field_name(schema_fields=None):
    """The Master JSON name used for quantity (e.g. ``"Quantity"``)."""
    fields = quantity_fields(_schema_fields(schema_fields))
    return fields[0]["name"] if fields else "Quantity"


def _schema_fields(schema_fields=None):
    if schema_fields is not None:
        return schema_fields
    from field_master.views import get_schema

    return get_schema().fields


def entry_quantity(item, schema_fields=None):
    """The quantity this one entry holds. Never a sum across entries."""
    return to_number(item.data.get(quantity_field_name(schema_fields)))


def set_quantity(item, amount, schema_fields=None, save=True):
    """Set this entry's own quantity (replaces, never accumulates)."""
    item.data[quantity_field_name(schema_fields)] = to_number(amount)
    if save:
        item.save(update_fields=["data", "updated_at"])
    return item.data[quantity_field_name(schema_fields)]


def sku_entries(sku):
    """Every entry carrying this SKU, newest first, each with its own quantity.

    Deliberately a list rather than a total: entries are not merged.
    """
    return list(sku.entries.order_by("-created_at"))


def entry_json(item, schema_fields=None):
    """One entry's complete JSON: its fields, its SKU and its own quantity."""
    return {
        "id": item.pk,
        **item.data,
        "sku": item.sku.code if item.sku else None,
        "sku_detail": dict(item.sku.data) if item.sku else {},
    }


def _as_number(total):
    """A Decimal aggregate as a plain number, sign intact.

    Deliberately not ``to_number``: that one parses loose user input by
    keeping only digits and dots, which throws away a leading minus - and
    every sale movement is negative.
    """
    if total is None:
        return 0
    number = float(total)
    return int(number) if number.is_integer() else number


def movement_total(item):
    """The net of every movement posted against this entry (0 when none)."""
    from django.db.models import Sum

    return _as_number(item.movements.aggregate(total=Sum("quantity"))["total"])


def available_quantity(item, schema_fields=None):
    """What this entry still holds: what came in, plus every movement since.

    Sales are negative movements and returns positive, so this is the number
    that matters on a shelf. ``entry_quantity`` stays the intake figure.
    """
    return entry_quantity(item, schema_fields) + movement_total(item)


def sold_quantity(item):
    """How much of this entry has gone out on invoices (a positive number)."""
    from django.db.models import Sum

    from .models import StockMovement

    total = item.movements.filter(kind=StockMovement.SALE).aggregate(
        total=Sum("quantity")
    )["total"]
    return -_as_number(total)


def returned_quantity(item):
    """How much of this entry has come back (a positive number)."""
    from django.db.models import Sum

    from .models import StockMovement

    total = item.movements.filter(kind=StockMovement.RETURN).aggregate(
        total=Sum("quantity")
    )["total"]
    return _as_number(total)
