"""Generates SKU codes from the Master JSON's "Include in SKU" fields.

Reads the Master JSON at call time, so it works with whatever fields are
marked ``include_in_sku`` today, tomorrow, or ever - nothing is hardcoded.

Composition is driven by two layers:
  * the global ``SkuFormat`` singleton (separator, component length, sequence
    padding, transform, uppercase), and
  * an optional per-field ``sku_config`` inside each field's Master JSON object
    (``order``, ``length``, ``transform``, ``uppercase``) that overrides the
    global defaults for that one field.
"""

from django.db import IntegrityError, transaction
from django.db.models import Max

from .models import SkuFormat, SkuNumber

# Fields with no explicit sku_config.order sort after those that have one.
_NO_ORDER = 10_000

# Only the first N "Include in SKU" fields (in order) get written into the
# code as literal text (e.g. Fabric/Sleeve/Color -> "COTT-HALF-BLAC"). Every
# field after that - Pattern, Grade, or whatever else gets added later - never
# appears as text. Those trailing fields are instead what the sequence number
# stands for, and that number is universal: the same combination of them gets
# the same number under any product, any item and any prefix (see number_for).
PREFIX_FIELD_COUNT = 3

# Quantity is stock information, not identity: two batches of the same variant
# are the same SKU whether there are 5 of them or 500. So a quantity field is
# held out of the SKU engine completely - it never reaches the code text, never
# takes part in the exact-match that picks a sequence number, and is never
# copied into Sku.data. It lives on the Item instead (see forms.registration_schema),
# where it is captured, displayed and added up quantity-wise.
#
# A field counts as quantity when the Master JSON marks it ``is_quantity``, or
# when its name reads as one - so ticking "Include in SKU" on Quantity by
# accident still cannot leak quantity into a code.
QUANTITY_FIELD_NAMES = {"quantity", "qty", "stock", "stock quantity"}


def is_quantity_field(field):
    """True when this Master JSON field holds a quantity."""
    if field.get("is_quantity"):
        return True
    return (field.get("name") or "").strip().lower() in QUANTITY_FIELD_NAMES


def is_sku_field(field):
    """True when a field genuinely takes part in SKU identity.

    "Include in SKU" alone is not enough: a quantity field is always excluded,
    no matter how it is configured.
    """
    return bool(field.get("include_in_sku")) and not is_quantity_field(field)


def quantity_fields(schema_fields):
    """Every quantity field in the schema, in Master JSON order."""
    return [f for f in schema_fields if is_quantity_field(f)]


def get_sku_fields(schema_fields):
    """All fields marked "Include in SKU", ordered by their ``sku_config.order``.

    Fields without an explicit order keep their Master JSON position (stable
    sort), landing after any explicitly-ordered fields.
    """
    sku_fields = [f for f in schema_fields if is_sku_field(f)]

    def sort_key(field):
        order = (field.get("sku_config") or {}).get("order")
        return order if isinstance(order, int) else _NO_ORDER

    return sorted(sku_fields, key=sort_key)


def sku_form_fields(schema_fields):
    """Fields rendered on the SKU Creation form: identity fields, then quantity.

    Quantity is on the form because stock is entered per variant, but it is
    split back out before anything is stored - see views.sku_add.
    """
    return get_sku_fields(schema_fields) + quantity_fields(schema_fields)


def prefix_sku_fields(schema_fields):
    """The first ``PREFIX_FIELD_COUNT`` SKU fields - written as literal text."""
    return get_sku_fields(schema_fields)[:PREFIX_FIELD_COUNT]


def _reduce(value, transform):
    """Keep only the characters allowed by ``transform``."""
    text = str(value or "")
    if transform == "alpha":
        return "".join(ch for ch in text if ch.isalpha())
    if transform == "digits":
        return "".join(ch for ch in text if ch.isdigit())
    # "alnum" and "full" both keep letters + digits (drop spaces/punctuation).
    return "".join(ch for ch in text if ch.isalnum())


def _component(value, length, transform):
    """One SKU segment from a single field value, per the resolved settings.

    Always uppercased - that's a fixed SKU rule (see SkuFormat.save()), not a
    per-field preference, so no field-level override can turn it off.
    """
    reduced = _reduce(value, transform)[:length]
    return reduced.upper()


def _resolved(field, fmt):
    """Merge a field's ``sku_config`` over the global ``SkuFormat`` defaults."""
    cfg = field.get("sku_config") or {}
    length = cfg.get("length")
    transform = cfg.get("transform")
    return {
        "length": length if isinstance(length, int) and length > 0 else fmt.component_length,
        "transform": transform or fmt.transform,
    }


def build_prefix(schema_fields, item_data, fmt=None):
    """Build the SKU prefix (e.g. ``COTT-HALF-BLAC``) for one item's data.

    Only the first ``PREFIX_FIELD_COUNT`` SKU fields become literal text.
    Anything beyond that never appears in the code itself - see
    ``PREFIX_FIELD_COUNT`` above. Empty components are dropped, so a blank
    value never produces a dangling separator.
    """
    fmt = fmt or SkuFormat.load()
    components = []
    for field in prefix_sku_fields(schema_fields):
        opts = _resolved(field, fmt)
        component = _component(item_data.get(field["name"]), **opts)
        if component:
            components.append(component)
    return fmt.separator.join(components)


def suffix_sku_fields(schema_fields):
    """The SKU fields past the prefix - the ones the number stands for."""
    return get_sku_fields(schema_fields)[PREFIX_FIELD_COUNT:]


def combination_key(schema_fields, item_data):
    """Normalise the non-prefix values into a lookup key plus readable detail.

    The key carries field names as well as values, so adding a new field later
    can never silently collide with an old combination. Matching is
    case-insensitive and whitespace-tolerant, so "A Grade" and "a  grade" are
    the same combination and share one number.
    """
    detail = {}
    parts = []
    for field in suffix_sku_fields(schema_fields):
        name = field["name"]
        value = item_data.get(name)
        text = " ".join(str(value or "").split())
        detail[name] = text
        parts.append(f"{name.strip().lower()}={text.lower()}")
    return "|".join(parts), detail


def number_for(schema_fields, item_data):
    """The sequence number for this combination - universally.

    Look the combination up first: if it has ever been numbered, under any
    product or prefix, that same number comes back. Only a combination seen
    for the first time consumes the next free number.
    """
    key, detail = combination_key(schema_fields, item_data)

    for _ in range(5):
        existing = SkuNumber.objects.filter(key=key).first()
        if existing:
            return existing.number

        next_number = (SkuNumber.objects.aggregate(Max("number"))["number__max"] or 0) + 1
        try:
            with transaction.atomic():
                return SkuNumber.objects.create(key=key, detail=detail, number=next_number).number
        except IntegrityError:
            # Another writer took that number (or the same key) - re-read.
            continue

    raise IntegrityError(f"Could not assign a SKU number for combination '{key}'.")


def _format_code(prefix, number, fmt):
    suffix = f"{number:0{fmt.sequence_padding}d}"
    return f"{prefix}{fmt.separator}{suffix}" if prefix else suffix


def find_matching_sku(sku_fields, data):
    """Return the existing Sku whose "Include in SKU" values exactly match
    ``data``, or ``None``.

    A given combination of variant detail maps to exactly one Sku code
    system-wide: two different products that happen to land on the same
    Fabric/Sleeve/Color (etc.) combo share that one Sku instead of minting a
    new sequence number for what is, detail-wise, the identical variant.

    This decides whether a SKU *row* is reused. The trailing number is a
    separate question, answered globally by ``number_for``.
    """
    from .models import Sku

    names = [f["name"] for f in sku_fields]
    for sku in Sku.objects.all():
        if all(sku.data.get(name) == data.get(name) for name in names):
            return sku
    return None


def generate_sku(schema_fields, item_data):
    """Build the SKU code for one variant: prefix text + universal number.

    The number comes from the combination of the non-prefix values alone, so a
    repeat of that combination anywhere in the system returns the same number,
    and a new combination takes the next one. Two SKUs can only produce the
    same code if their prefix *and* their combination match - which makes them
    the same variant, and ``find_matching_sku`` reuses that row instead of
    generating at all.
    """
    from .models import Sku

    fmt = SkuFormat.load()
    prefix = build_prefix(schema_fields, item_data, fmt)
    code = _format_code(prefix, number_for(schema_fields, item_data), fmt)

    clash = Sku.objects.filter(code=code).first()
    if clash:
        # Only reachable with hand-edited/legacy rows; surface it rather than
        # silently attaching this variant to someone else's code.
        raise IntegrityError(f"Generated code '{code}' already belongs to SKU #{clash.pk}.")
    return code
