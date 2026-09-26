import json

from django.contrib import admin
from django.utils.html import format_html

from .models import Barcode, Entry, Item, Sku, SkuFormat, SkuNumber
from .quantity import entry_json, entry_quantity, sku_entries


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    """Entries: one row per press of Save - a product and the SKUs saved with it.

    Display grouping only. Nothing calculates from this table: quantity, SKU
    codes, numbering and barcodes all work off the Item rows (its ``lines``).
    """

    list_display = ("pk", "product", "sku_count", "sku_codes", "created_at")
    search_fields = ("product",)
    readonly_fields = ("created_at",)

    @admin.display(description="SKUs")
    def sku_count(self, obj):
        return obj.lines.count()

    @admin.display(description="SKU Codes")
    def sku_codes(self, obj):
        return ", ".join(line.sku.code for line in obj.lines.all() if line.sku) or "-"


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    """Products: every entry, flat.

    One row is one entry: product data + its SKU + that entry's own quantity.
    Taking the same product and SKU in again adds another row here rather than
    changing this one - entry quantities are never merged.
    """

    list_display = ("pk", "entry", "product_name", "sku_code", "quantity", "created_at")
    list_filter = ("sku",)
    search_fields = ("data", "sku__code")
    readonly_fields = ("complete_json", "created_at", "updated_at")

    @admin.display(description="Product Name")
    def product_name(self, obj):
        return obj.data.get("Product Name") or "-"

    @admin.display(description="Quantity (this entry)")
    def quantity(self, obj):
        return entry_quantity(obj)

    @admin.display(description="SKU", ordering="sku__code")
    def sku_code(self, obj):
        return obj.sku.code if obj.sku else "-"

    @admin.display(description="Complete JSON")
    def complete_json(self, obj):
        """This entry exactly as stored: its fields, its SKU, its own quantity."""
        return format_html(
            '<pre style="white-space:pre-wrap;margin:0;">{}</pre>',
            json.dumps(entry_json(obj), indent=2, default=str),
        )


@admin.register(Sku)
class SkuAdmin(admin.ModelAdmin):
    """SKUs: one variant combination and its generated code.

    ``data`` holds variant detail only - no quantity and no cost. The same
    code is reused by every intake of that variant; each intake is its own
    entry in the Products table, with its own quantity.
    """

    list_display = ("code", "variant_detail", "entry_count", "entry_quantities", "created_at")
    search_fields = ("code", "data")
    readonly_fields = ("created_at",)

    @admin.display(description="Variant Detail")
    def variant_detail(self, obj):
        return ", ".join(f"{key}: {value}" for key, value in obj.data.items()) or "-"

    @admin.display(description="Entries")
    def entry_count(self, obj):
        """How many Products-table entries carry this code."""
        return obj.entries.count()

    @admin.display(description="Quantity per entry (not merged)")
    def entry_quantities(self, obj):
        rows = [f"#{e.pk}: {entry_quantity(e)}" for e in sku_entries(obj)]
        return ", ".join(rows) or "-"


@admin.register(SkuNumber)
class SkuNumberAdmin(admin.ModelAdmin):
    """The universal combination -> number registry behind every SKU code."""

    list_display = ("number", "key", "created_at")
    search_fields = ("key",)
    readonly_fields = ("created_at",)


@admin.register(Barcode)
class BarcodeAdmin(admin.ModelAdmin):
    """Our label and the barcode the material arrived with, side by side."""

    list_display = ("value", "source_value", "entry", "object_type", "created_at")
    search_fields = ("value", "source_value")
    readonly_fields = ("created_at",)
admin.site.register(SkuFormat)
