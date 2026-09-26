from django.db import models

from core.object_types import CHOICES as OBJECT_TYPE_CHOICES
from core.object_types import ITEM as OBJECT_TYPE_ITEM

# How a field value is reduced to its SKU component.
TRANSFORM_CHOICES = [
    ("alpha", "Letters only"),
    ("alnum", "Letters + digits"),
    ("digits", "Digits only"),
    ("full", "Keep as-is (alnum)"),
]


class SkuFormat(models.Model):
    """Global SKU-format defaults (a single row).

    Per-field overrides live in each field's ``sku_config`` inside the Master
    JSON; anything left blank there falls back to these global values.

    ``separator`` and ``uppercase`` are fixed SKU rules, not user preferences:
    every SKU is always uppercase and always hyphen-separated. ``save()``
    pins both, so no code path (including the admin) can change them.
    """

    separator = models.CharField(max_length=5, default="-")
    component_length = models.PositiveSmallIntegerField(default=3)
    sequence_padding = models.PositiveSmallIntegerField(default=3)
    transform = models.CharField(max_length=10, choices=TRANSFORM_CHOICES, default="alnum")
    uppercase = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "SKU format"
        verbose_name_plural = "SKU format"

    def __str__(self):
        return "SKU Format"

    def save(self, *args, **kwargs):
        self.separator = "-"
        self.uppercase = True
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Return the singleton row, creating it with defaults on first use."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Entry(models.Model):
    """One save from an add page: a product and every SKU line saved with it.

    Purely a display grouping. Pressing Save once on Add New / Add Existing
    Product marks one Entry, and the SKU lines of that save (``lines``, the
    Item rows) hang off it - so the Item Display page can show a product, its
    entries, and each entry's SKUs.

    Nothing calculates from this table. Quantity, SKU codes, barcodes and the
    numbering registry all keep working off the Item rows exactly as before;
    removing an Entry would change what the page looks like, never what
    anything computes.
    """

    product = models.CharField(max_length=255, blank=True)
    data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name_plural = "entries"

    def __str__(self):
        return f"Entry #{self.pk} - {self.product or 'unnamed'}"


class Item(models.Model):
    """One product entry: product data + one SKU + that entry's own quantity.

    ``data`` holds every field value keyed by field name, exactly as defined
    by the Master JSON at the time the entry was saved. No field is modelled
    as a column here on purpose: the schema is dynamic and lives in
    field_master.MasterSchema.

    One entry carries at most one SKU. Adding another SKU - or taking the same
    variant in again - creates its own separate entry row, and every entry
    lives directly in the Products table. Quantities of separate entries are
    never merged: each entry keeps the quantity it was entered with.
    """

    data = models.JSONField(default=dict, blank=True)
    entry = models.ForeignKey(
        Entry,
        null=True,
        blank=True,
        related_name="lines",
        on_delete=models.SET_NULL,
    )
    sku = models.ForeignKey(
        "Sku",
        null=True,
        blank=True,
        related_name="entries",
        on_delete=models.SET_NULL,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Item #{self.pk}"


class SkuNumber(models.Model):
    """The universal registry of SKU sequence numbers.

    A SKU code's trailing number is decided by one thing only: the combination
    of its non-prefix "Include in SKU" values (e.g. Pattern=Plain, Grade=A
    Grade). That mapping is global - independent of the product, the item and
    the prefix words in front of it:

        (Plain, A Grade) -> 001   COT-HAL-BLA-001
        (Plain, B Grade) -> 002   COT-HAL-BLA-002
        (Plain, A Grade) -> 001   LYC-FUL-RED-001   <- same combo, same number

    ``key`` is the normalised combination (case/space-insensitive) and is what
    makes a repeat hit the same number; ``detail`` keeps the readable values
    behind it. A combination never seen before takes the next free number.
    """

    key = models.CharField(max_length=255, unique=True)
    detail = models.JSONField(default=dict, blank=True)
    number = models.PositiveIntegerField(unique=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("number",)
        verbose_name = "SKU number"

    def __str__(self):
        return f"{self.number:03d} - {self.key or '(no variant detail)'}"


class Sku(models.Model):
    """One SKU variant, identified purely by its "Include in SKU" field values.

    A given combination of variant detail (e.g. Fabric=Cotton, Sleeve=Half,
    Color=Blue) maps to exactly one Sku row and one code, no matter how many
    entries use it - the same combination always comes back to this same code.
    ``data`` holds only the values for those fields: no quantity, no cost.

    Stock is not held here. Each intake is its own entry in the Products table
    (``entries``), carrying its own quantity and its own cost.
    """

    data = models.JSONField(default=dict, blank=True)
    code = models.CharField(max_length=120, unique=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code


class Barcode(models.Model):
    """The single Barcode record for one entry.

    Barcodes are per entry, not per SKU: two intakes of the same variant share
    a code but are different stock at different cost, so each entry carries its
    own label. ``value`` is the entry's SKU code with the entry number on the
    end (e.g. ``COT-HAL-BLA-001-33``) and ``image`` is a Code128 rendering of
    it with the value printed underneath. Scanning it resolves straight back to
    this one entry - its quantity, its cost, its product.

    When the material was registered from the scan panel, the code that was
    scanned is kept in ``source_value``: the old barcode and ours, side by
    side, mapping to each other.
    """

    entry = models.OneToOneField(Item, related_name="barcode", on_delete=models.CASCADE)
    object_type = models.CharField(max_length=2, choices=OBJECT_TYPE_CHOICES, default=OBJECT_TYPE_ITEM)
    object_id = models.PositiveIntegerField()
    value = models.CharField(max_length=128, unique=True)
    # The barcode the material arrived with - a vendor's EAN off the carton,
    # say - kept beside our own value so the two map to each other. Scanning
    # either one lands on this same entry. Blank for stock we labelled first.
    source_value = models.CharField(max_length=128, blank=True, db_index=True)
    image = models.ImageField(upload_to="barcodes/")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.value
