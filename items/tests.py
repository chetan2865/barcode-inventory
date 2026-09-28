"""Stock movement: what an entry holds after sales and returns.

These cover the arithmetic the Products page and the Returns page both read
from, and the rule that an entry's intake figure is never rewritten.
"""

from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from field_master.views import get_schema
from items import quantity as quantity_engine
from items import sku as sku_engine
from items.models import Entry, Item, StockMovement
from items.views import _create_entries

SEED = Path(settings.BASE_DIR) / "seed" / "initial_setup.json"


class SchemaFixtureMixin:
    """Run against the real field schema, not the migrations' starting one.

    A test database is built from migrations, whose starting schema has no
    variant fields at all - so without this the SKU and size behaviour would
    be tested against a schema the application never actually runs on.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("loaddata", str(SEED), verbosity=0)


class StockMovementTests(SchemaFixtureMixin, TestCase):
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


class ReturnsPageTests(SchemaFixtureMixin, TestCase):
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


class SizeRunTests(SchemaFixtureMixin, TestCase):
    """One pass of the add form, several sizes, one entry per size."""

    def setUp(self):
        self.schema = get_schema().fields
        self.qty_name = quantity_engine.quantity_field_name(self.schema)
        self.size = sku_engine.size_field(self.schema)
        self.options = sku_engine.size_options(self.schema)
        self.form_fields = sku_engine.sku_form_fields(self.schema)

    def _post(self, run):
        """Post the add form with a size run, as the page submits it."""
        from items.forms import input_name, registration_schema, visible_fields

        data = {}
        for position, field in enumerate(visible_fields(registration_schema(self.schema))):
            value = ""
            if field["name"] == "Product Name":
                value = "Run Tee"
            elif field["name"] == "HSN":
                value = "6109"
            elif field["type"] == "number":
                value = "100"
            elif field["type"] == "dropdown":
                options = (field.get("configuration") or {}).get("options") or []
                value = options[0] if options else ""
            data[input_name(position)] = value

        # SKU attributes, chosen once for the whole run.
        for position, field in enumerate(self.form_fields):
            if field["name"] in {self.size["name"], self.qty_name}:
                continue
            options = (field.get("configuration") or {}).get("options") or []
            data[f"sku_0_{input_name(position)}"] = options[0] if options else "1"

        for option_index, amount in run.items():
            data[f"sku_0_qty_{option_index}"] = str(amount)

        return self.client.post(reverse("items:add"), data, follow=True)

    def test_schema_has_a_size_axis(self):
        self.assertIsNotNone(self.size)
        self.assertIn("M", self.options)

    def test_one_pass_creates_one_entry_per_size(self):
        before = Item.objects.count()
        # Sizes at index 1, 2, 3 -> S, M, L
        self._post({1: 8, 2: 12, 3: 6})
        created = Item.objects.count() - before
        self.assertEqual(created, 3)

    def test_each_size_keeps_its_own_quantity(self):
        self._post({1: 8, 2: 12, 3: 6})
        rows = Item.objects.select_related("sku").order_by("-pk")[:3]
        # Size is variant identity, so it lives on the Sku; the quantity is
        # the entry's own and lives on the Item.
        by_size = {
            r.sku.data.get(self.size["name"]): r.data.get(self.qty_name) for r in rows
        }
        self.assertEqual(by_size[self.options[1]], 8)
        self.assertEqual(by_size[self.options[2]], 12)
        self.assertEqual(by_size[self.options[3]], 6)

    def test_each_size_gets_its_own_sku_and_barcode(self):
        self._post({1: 8, 2: 12})
        rows = list(Item.objects.order_by("-pk")[:2])
        codes = {r.sku.code for r in rows}
        self.assertEqual(len(codes), 2, "sizes must not share one SKU code")
        for row in rows:
            self.assertTrue(hasattr(row, "barcode"))

    def test_sizes_left_blank_create_nothing(self):
        before = Item.objects.count()
        self._post({1: 0, 2: 5, 3: ""})
        self.assertEqual(Item.objects.count() - before, 1)

    def test_the_whole_run_shares_one_entry(self):
        self._post({1: 8, 2: 12, 3: 6})
        rows = Item.objects.order_by("-pk")[:3]
        self.assertEqual(len({r.entry_id for r in rows}), 1)
