"""Stock movement: what an entry holds after sales and returns.

These cover the arithmetic the Products page and the Returns page both read
from, and the rule that an entry's intake figure is never rewritten.
"""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from field_master.views import get_schema
from items import quantity as quantity_engine
from items import sku as sku_engine
from items.models import Entry, Item, StockMovement
from items.views import _create_entries


class StockMovementTests(TestCase):
    def setUp(self):
        self.schema = get_schema().fields
        self.qty_name = quantity_engine.quantity_field_name(self.schema)
        sku_fields = sku_engine.get_sku_fields(self.schema)

        product = {field["name"]: None for field in self.schema}
        product.update({"Product Name": "Test Tee", "HSN": "6109"})
        block = {field["name"]: None for field in sku_fields}
        block[self.qty_name] = 100
        for field in sku_fields:
            if field["type"] == "dropdown":
                options = (field.get("configuration") or {}).get("options") or []
                if options:
                    block[field["name"]] = options[0]

        _create_entries(product, [block], self.schema, sku_fields)
        self.entry = Item.objects.order_by("-pk").first()

    def test_intake_is_the_starting_quantity(self):
        self.assertEqual(quantity_engine.entry_quantity(self.entry, self.schema), 100)
        self.assertEqual(quantity_engine.available_quantity(self.entry, self.schema), 100)
        self.assertEqual(quantity_engine.sold_quantity(self.entry), 0)

    def test_a_sale_reduces_what_is_available(self):
        StockMovement.objects.create(
            entry=self.entry, kind=StockMovement.SALE, quantity=Decimal("-30")
        )
        self.assertEqual(quantity_engine.available_quantity(self.entry, self.schema), 70)
        self.assertEqual(quantity_engine.sold_quantity(self.entry), 30)

    def test_a_sale_never_rewrites_the_intake_figure(self):
        StockMovement.objects.create(
            entry=self.entry, kind=StockMovement.SALE, quantity=Decimal("-30")
        )
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.data[self.qty_name], 100)

    def test_a_return_puts_stock_back(self):
        StockMovement.objects.create(
            entry=self.entry, kind=StockMovement.SALE, quantity=Decimal("-30")
        )
        StockMovement.objects.create(
            entry=self.entry, kind=StockMovement.RETURN, quantity=Decimal("10")
        )
        self.assertEqual(quantity_engine.available_quantity(self.entry, self.schema), 80)
        self.assertEqual(quantity_engine.sold_quantity(self.entry), 30)
        self.assertEqual(quantity_engine.returned_quantity(self.entry), 10)

    def test_barcode_is_minted_when_the_entry_is_saved(self):
        self.assertTrue(hasattr(self.entry, "barcode"))
        self.assertTrue(self.entry.barcode.value.endswith(f"-{self.entry.pk}"))


class ReturnsPageTests(TestCase):
    def setUp(self):
        self.schema = get_schema().fields
        self.qty_name = quantity_engine.quantity_field_name(self.schema)
        sku_fields = sku_engine.get_sku_fields(self.schema)

        product = {field["name"]: None for field in self.schema}
        product.update({"Product Name": "Return Tee", "HSN": "6109"})
        block = {field["name"]: None for field in sku_fields}
        block[self.qty_name] = 50
        for field in sku_fields:
            if field["type"] == "dropdown":
                options = (field.get("configuration") or {}).get("options") or []
                if options:
                    block[field["name"]] = options[0]

        _create_entries(product, [block], self.schema, sku_fields)
        self.entry = Item.objects.order_by("-pk").first()
        self.code = self.entry.barcode.value

    def test_page_opens(self):
        self.assertEqual(self.client.get(reverse("items:returns")).status_code, 200)

    def test_scanning_a_barcode_shows_the_entry(self):
        response = self.client.get(reverse("items:returns"), {"value": self.code})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["entry"].pk, self.entry.pk)
        self.assertEqual(response.context["available"], 50)

    def test_returning_more_than_was_sold_is_refused(self):
        StockMovement.objects.create(
            entry=self.entry, kind=StockMovement.SALE, quantity=Decimal("-5")
        )
        self.client.post(
            reverse("items:returns"), {"value": self.code, "quantity": "9"}
        )
        # Nothing invented: still only the one sale movement.
        self.assertEqual(self.entry.movements.count(), 1)
        self.assertEqual(quantity_engine.available_quantity(self.entry, self.schema), 45)

    def test_accepting_a_return_restores_stock(self):
        StockMovement.objects.create(
            entry=self.entry, kind=StockMovement.SALE, quantity=Decimal("-20")
        )
        self.client.post(
            reverse("items:returns"),
            {"value": self.code, "quantity": "8", "note": "size exchange"},
        )
        self.assertEqual(quantity_engine.available_quantity(self.entry, self.schema), 38)
        self.assertEqual(quantity_engine.returned_quantity(self.entry), 8)
