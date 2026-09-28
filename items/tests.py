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
        # Size is not SKU identity: it rides in the entry's own data, beside
        # the quantity.
        by_size = {
            r.data.get(self.size["name"]): r.data.get(self.qty_name) for r in rows
        }
        self.assertEqual(by_size[self.options[1]], 8)
        self.assertEqual(by_size[self.options[2]], 12)
        self.assertEqual(by_size[self.options[3]], 6)

    def test_sizes_share_a_sku_code_but_get_their_own_barcode(self):
        self._post({1: 8, 2: 12})
        rows = list(Item.objects.select_related("sku").order_by("-pk")[:2])
        codes = {r.sku.code for r in rows}
        self.assertEqual(len(codes), 1, "size is not part of SKU identity")
        # The barcode carries the entry id, so each size still scans uniquely.
        barcodes = {r.barcode.value for r in rows}
        self.assertEqual(len(barcodes), 2)

    def test_sizes_left_blank_create_nothing(self):
        before = Item.objects.count()
        self._post({1: 0, 2: 5, 3: ""})
        self.assertEqual(Item.objects.count() - before, 1)

    def test_the_whole_run_shares_one_entry(self):
        self._post({1: 8, 2: 12, 3: 6})
        rows = Item.objects.order_by("-pk")[:3]
        self.assertEqual(len({r.entry_id for r in rows}), 1)


class HiddenSkuFieldTests(SchemaFixtureMixin, TestCase):
    """Retiring a SKU field: new SKUs drop it, existing ones keep their codes."""

    def setUp(self):
        self.schema = get_schema().fields
        self.sku_names = [f["name"] for f in sku_engine.get_sku_fields(self.schema)]

    def _hide(self, name):
        from field_master.views import get_schema as fm_schema

        schema = fm_schema()
        fields = list(schema.fields)
        index = next(i for i, f in enumerate(fields) if f["name"] == name)
        response = self.client.post(reverse("field_master:toggle_hide", args=[index]))
        return response, index

    def test_a_sku_field_starts_in_the_sku(self):
        self.assertIn("Pattern", self.sku_names)

    def test_hiding_drops_it_from_new_skus(self):
        self._hide("Pattern")
        names = [f["name"] for f in sku_engine.get_sku_fields(get_schema().fields)]
        self.assertNotIn("Pattern", names)

    def test_hiding_clears_mandatory(self):
        # A hidden field is never rendered, so it must not stay required.
        self._hide("Pattern")
        field = next(f for f in get_schema().fields if f["name"] == "Pattern")
        self.assertTrue(field["hide"])
        self.assertFalse(field["mandatory"])

    def test_the_field_is_not_deleted(self):
        self._hide("Pattern")
        names = [f["name"] for f in get_schema().fields]
        self.assertIn("Pattern", names)

    def test_existing_skus_keep_their_data_and_code(self):
        qty_name = quantity_engine.quantity_field_name(self.schema)
        sku_fields = sku_engine.get_sku_fields(self.schema)
        product = {f["name"]: None for f in self.schema}
        product.update({"Product Name": "Retire Tee", "HSN": "6109"})
        block = {f["name"]: None for f in sku_fields}
        block[qty_name] = 10
        for f in sku_fields:
            options = (f.get("configuration") or {}).get("options") or []
            if options:
                block[f["name"]] = options[0]
        _create_entries(product, [block], self.schema, sku_fields)

        row = Item.objects.select_related("sku").order_by("-pk").first()
        code_before = row.sku.code
        data_before = dict(row.sku.data)
        self.assertIn("Pattern", data_before)

        self._hide("Pattern")

        row.refresh_from_db()
        self.assertEqual(row.sku.code, code_before)
        self.assertEqual(row.sku.data, data_before)

    def test_showing_it_again_restores_it(self):
        self._hide("Pattern")
        self._hide("Pattern")
        names = [f["name"] for f in sku_engine.get_sku_fields(get_schema().fields)]
        self.assertIn("Pattern", names)


class HideRoundTripTests(SchemaFixtureMixin, TestCase):
    """Showing a field again must leave it as it was before it was hidden."""

    def _toggle(self, name):
        from field_master.views import get_schema as fm_schema

        fields = list(fm_schema().fields)
        index = next(i for i, f in enumerate(fields) if f["name"] == name)
        self.client.post(reverse("field_master:toggle_hide", args=[index]))

    def test_mandatory_survives_a_hide_and_show(self):
        before = next(f for f in get_schema().fields if f["name"] == "Pattern")
        self.assertTrue(before["mandatory"])

        self._toggle("Pattern")
        hidden = next(f for f in get_schema().fields if f["name"] == "Pattern")
        self.assertFalse(hidden["mandatory"], "a hidden field cannot be required")

        self._toggle("Pattern")
        after = next(f for f in get_schema().fields if f["name"] == "Pattern")
        self.assertTrue(after["mandatory"], "mandatory must come back")
        self.assertNotIn("mandatory_before_hide", after)

    def test_an_optional_field_stays_optional(self):
        from field_master.views import get_schema as fm_schema

        schema = fm_schema()
        fields = list(schema.fields)
        index = next(i for i, f in enumerate(fields) if f["name"] == "Pattern")
        fields[index] = {**fields[index], "mandatory": False}
        schema.fields = fields
        schema.save()

        self._toggle("Pattern")
        self._toggle("Pattern")
        after = next(f for f in get_schema().fields if f["name"] == "Pattern")
        self.assertFalse(after["mandatory"])


class TagPrintingTests(SchemaFixtureMixin, TestCase):
    """Tags follow the shelf: sold pieces lose theirs, returns earn one back."""

    def setUp(self):
        self.schema = get_schema().fields
        qty_name = quantity_engine.quantity_field_name(self.schema)
        sku_fields = sku_engine.get_sku_fields(self.schema)

        product = {f["name"]: None for f in self.schema}
        product.update({"Product Name": "Tag Tee", "HSN": "6109"})
        block = {f["name"]: None for f in sku_fields}
        block[qty_name] = 20
        for f in sku_fields:
            options = (f.get("configuration") or {}).get("options") or []
            if options:
                block[f["name"]] = options[0]

        _create_entries(product, [block], self.schema, sku_fields)
        self.entry = Item.objects.order_by("-pk").first()
        self.url = reverse("items:labels", args=[self.entry.pk])

    def _tag_count(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return response.context["copies"], response.context["available"]

    def test_every_piece_is_tagged_before_anything_sells(self):
        copies, available = self._tag_count()
        self.assertEqual(copies, 20)
        self.assertEqual(available, 20)

    def test_sold_pieces_are_not_tagged_again(self):
        StockMovement.objects.create(
            entry=self.entry, kind=StockMovement.SALE, quantity=Decimal("-8")
        )
        copies, available = self._tag_count()
        self.assertEqual(copies, 12)
        self.assertEqual(available, 12)

    def test_a_return_makes_a_tag_printable_again(self):
        StockMovement.objects.create(
            entry=self.entry, kind=StockMovement.SALE, quantity=Decimal("-8")
        )
        StockMovement.objects.create(
            entry=self.entry, kind=StockMovement.RETURN, quantity=Decimal("3")
        )
        copies, available = self._tag_count()
        self.assertEqual(copies, 15)
        self.assertEqual(available, 15)

    def test_nothing_is_tagged_once_the_lot_is_sold_out(self):
        StockMovement.objects.create(
            entry=self.entry, kind=StockMovement.SALE, quantity=Decimal("-20")
        )
        copies, available = self._tag_count()
        self.assertEqual(copies, 0)
        self.assertEqual(available, 0)
        self.assertEqual(len(self.client.get(self.url).context["tags"]), 0)

    def test_asking_for_more_than_the_shelf_holds_is_capped(self):
        StockMovement.objects.create(
            entry=self.entry, kind=StockMovement.SALE, quantity=Decimal("-15")
        )
        copies, available = self._tag_count(copies="20")
        self.assertEqual(available, 5)
        self.assertEqual(copies, 5, "must not print tags for stock that is gone")

    def test_a_short_reprint_is_allowed(self):
        copies, _ = self._tag_count(copies="3")
        self.assertEqual(copies, 3)
