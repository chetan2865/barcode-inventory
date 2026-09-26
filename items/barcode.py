"""Barcode payload/image generation and scan resolution for entries.

Two levels of label:

* **Lot label** - one per entry, for the box the lot ships in:
  ``<sku code>-<entry id>`` (e.g. ``COT-HAL-BLU-002-29``).
* **Unit labels** - one per physical piece inside that lot, for the items
  themselves: the lot value with a running object id on the end,
  ``COT-HAL-BLU-002-29-1`` ... ``-29-30`` for a lot of 30.

Unit labels are not stored: an entry of 30 pieces would mean 30 extra rows
carrying no information that ``lot value + object id`` does not already give.
They are rendered on demand for download, and ``resolve`` reads the object id
straight back off a scanned value.
"""

import io
import re

import barcode as barcode_lib
from barcode.writer import ImageWriter
from django.core.files.base import ContentFile

from core.object_types import ITEM as OBJECT_TYPE_ITEM
from core.object_types import SKU as OBJECT_TYPE_SKU

_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]+")

# Where a code scanned off someone else's packaging is kept, when a line was
# registered straight from the scan panel. Our own labels are generated, so
# this is the only way an outside barcode (an EAN off a vendor's box, say)
# leads back to the material it was registered as.
SOURCE_CODE_KEY = "scanned_code"


def build_value(entry):
    """The barcode payload: ``<sku code>-<entry id>``.

    The entry number is what makes two intakes of one variant distinguishable
    on the shelf; the SKU code in front keeps the label readable.
    """
    if entry.sku_id is None:
        return None
    return f"{entry.sku.code}-{entry.pk}"


def unit_value(entry, number):
    """The label for one piece inside a lot: lot value + object id."""
    lot = build_value(entry)
    return None if lot is None else f"{lot}-{number}"


def unit_count(entry):
    """How many unit labels this lot needs - its own quantity, whole pieces."""
    from .quantity import entry_quantity

    return max(0, int(entry_quantity(entry)))


def generate_image(value):
    """Render ``value`` as a Code128 barcode PNG. Returns ``(filename, ContentFile)``."""
    code = barcode_lib.get("code128", value, writer=ImageWriter())
    buffer = io.BytesIO()
    # write_text=True prints the human-readable value beneath the bars.
    code.write(buffer, options={"write_text": True})
    safe = _FILENAME_SAFE.sub("-", value) or "barcode"
    return f"{safe}.png", ContentFile(buffer.getvalue())


def source_code(entry):
    """The outside barcode this entry was registered from, if any."""
    return (entry.data.get(SOURCE_CODE_KEY) or "").strip()


def create_barcode_for_entry(entry):
    """Create (or return the existing) Barcode record for one entry."""
    from .models import Barcode

    existing = getattr(entry, "barcode", None)
    if existing:
        return existing

    value = build_value(entry)
    if value is None:
        return None

    filename, content = generate_image(value)
    record = Barcode(
        entry=entry,
        object_type=OBJECT_TYPE_ITEM,
        object_id=entry.pk,
        value=value,
        source_value=source_code(entry),
    )
    record.image.save(filename, content, save=False)
    record.save()
    return record


def sync_barcode_for_entry(entry):
    """Keep an entry's barcode in step with its SKU.

    Creates one if missing; regenerates value and image if the entry's SKU
    changed underneath it.
    """
    existing = getattr(entry, "barcode", None)
    if existing is None:
        return create_barcode_for_entry(entry)

    source = source_code(entry)
    value = build_value(entry)

    if value is None or existing.value == value:
        # Value unchanged, but the mapping to the old barcode may not be set yet.
        if existing.source_value != source:
            existing.source_value = source
            existing.save(update_fields=["source_value"])
        return existing

    filename, content = generate_image(value)
    existing.value = value
    existing.object_id = entry.pk
    existing.source_value = source
    existing.image.save(filename, content, save=False)
    existing.save()
    return existing


def resolve(value):
    """Decode a scanned value and load what it points at.

    Primary path: an entry barcode (``<sku code>-<entry id>``), which resolves
    to that one entry - its own quantity and cost. Falling back, a bare SKU
    code still resolves to the SKU itself (useful when reading a code printed
    before entry labels, or typing a code by hand), as do legacy
    ``<Object Type>|<Primary Key>`` payloads. Returns ``None`` if nothing
    matches.
    """
    from .models import Barcode, Sku

    value = (value or "").strip()
    if not value:
        return None

    # Primary: an entry's own barcode.
    record = (
        Barcode.objects.select_related("entry", "entry__sku")
        .filter(value=value)
        .first()
    )
    if record:
        return _entry_result(record.entry)

    # A unit label: the lot value with an object id on the end.
    lot_value, _, suffix = value.rpartition("-")
    if suffix.isdigit() and lot_value:
        record = (
            Barcode.objects.select_related("entry", "entry__sku")
            .filter(value=lot_value)
            .first()
        )
        if record:
            return _entry_result(record.entry, unit=int(suffix))

    # Fallback: the SKU code itself, with no single entry implied.
    sku = Sku.objects.prefetch_related("entries").filter(code=value).first()
    if sku:
        return _sku_result(sku)

    # The old barcode the material came in with, mapped beside ours.
    record = (
        Barcode.objects.select_related("entry", "entry__sku")
        .filter(source_value=value)
        .order_by("-created_at")
        .first()
    )
    if record:
        return _entry_result(record.entry, source=value)

    # Same mapping for a line whose label has not been generated yet.
    from .models import Item

    line = (
        Item.objects.select_related("sku")
        .filter(**{f"data__{SOURCE_CODE_KEY}": value})
        .order_by("-created_at")
        .first()
    )
    if line:
        return _entry_result(line, source=value)

    # Fallback: legacy "<object_type>|<pk>" payloads.
    parts = value.split("|")
    if len(parts) == 2 and parts[1].isdigit():
        if parts[0] == OBJECT_TYPE_SKU:
            sku = Sku.objects.prefetch_related("entries").filter(pk=int(parts[1])).first()
            return _sku_result(sku) if sku else None
        if parts[0] == OBJECT_TYPE_ITEM:
            entry = Item.objects.select_related("sku").filter(pk=int(parts[1])).first()
            return _entry_result(entry) if entry else None

    return None


def _entry_result(entry, unit=None, source=None):
    """Resolve payload for a scanned lot or unit label.

    ``unit`` is the object id read off a unit label - which piece of the lot
    was scanned. It is ``None`` for the lot label itself. ``source`` is set
    when the scan came in on the old, outside barcode rather than ours.
    """
    from .quantity import entry_quantity

    quantity = entry_quantity(entry)
    return {
        "object_type": OBJECT_TYPE_ITEM,
        "object_id": entry.pk,
        "entry": entry,
        "entry_id": entry.pk,
        "quantity": quantity,
        "unit": unit,
        # A unit id past the lot's quantity means a stale or mis-printed label.
        "unit_in_range": unit is None or 1 <= unit <= int(quantity),
        "source_scan": source,
        "source_code": source_code(entry),
        "sku": entry.sku,
        "sku_id": entry.sku_id,
    }


def _sku_result(sku):
    """Resolve payload for a bare SKU code: the variant, no single entry."""
    return {
        "object_type": OBJECT_TYPE_SKU,
        "object_id": sku.pk,
        "entry": None,
        "entry_id": None,
        "quantity": None,
        "unit": None,
        "unit_in_range": True,
        "source_scan": None,
        "source_code": "",
        "sku": sku,
        "sku_id": sku.pk,
    }
