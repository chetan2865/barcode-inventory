"""Populate a database with a realistic apparel catalogue.

Everything is created through the same engines the UI uses - ``_create_entries``
for the product/entry/SKU hierarchy and ``barcode`` for the labels - so SKU
codes, the global SkuNumber registry and the per-entry barcodes come out
exactly as they would had each item been typed in by hand.

Values respect the field schema: dropdowns only use options the schema
defines, so nothing here could have been rejected by the registration form.

    python manage.py seed_catalogue           # add the catalogue
    python manage.py seed_catalogue --flush   # replace whatever is there
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from field_master.views import get_schema
from items import barcode as barcode_engine
from items import sku as sku_engine
from items.models import Barcode, Entry, Item, Sku, SkuNumber
from items.views import _create_entries

# GST on Indian apparel: 5% up to Rs 1,000, 12% above it.
CATALOGUE = [
    {
        "product": "Classic Crew Neck T-Shirt",
        "hsn": "6109",
        "rate": "799.00",
        "cost": "310.00",
        "gst": "5%",
        "skus": [
            {"Fabric": "Cotton", "Sleeve": "Half Sleeve", "Color": "Black", "Pattern": "Plain", "material": 180, "Quantity": 120},
            {"Fabric": "Cotton", "Sleeve": "Half Sleeve", "Color": "Blue", "Pattern": "Plain", "material": 180, "Quantity": 90},
            {"Fabric": "Cotton", "Sleeve": "Half Sleeve", "Color": "Black", "Pattern": "Striped", "material": 180, "Quantity": 60},
        ],
    },
    {
        "product": "Premium Pique Polo",
        "hsn": "6105",
        "rate": "1299.00",
        "cost": "520.00",
        "gst": "12%",
        "skus": [
            {"Fabric": "Cotton", "Sleeve": "Half Sleeve", "Color": "Blue", "Pattern": "Plain", "material": 220, "Quantity": 75},
            {"Fabric": "Cotton", "Sleeve": "Half Sleeve", "Color": "Black", "Pattern": "Plain", "material": 220, "Quantity": 65},
        ],
    },
    {
        "product": "Oxford Casual Shirt",
        "hsn": "6205",
        "rate": "1699.00",
        "cost": "690.00",
        "gst": "12%",
        "skus": [
            {"Fabric": "Cotton", "Sleeve": "Full Sleeve", "Color": "Blue", "Pattern": "Checked", "material": 160, "Quantity": 48},
            {"Fabric": "Cotton", "Sleeve": "Full Sleeve", "Color": "Blue", "Pattern": "Striped", "material": 160, "Quantity": 42},
            {"Fabric": "Cotton", "Sleeve": "Full Sleeve", "Color": "Black", "Pattern": "Plain", "material": 160, "Quantity": 36},
        ],
    },
    {
        "product": "Slim Fit Stretch Chinos",
        "hsn": "6203",
        "rate": "1899.00",
        "cost": "780.00",
        "gst": "12%",
        "skus": [
            {"Fabric": "Lycra", "Sleeve": "Full Sleeve", "Color": "Black", "Pattern": "Plain", "material": 240, "Quantity": 54},
            {"Fabric": "Lycra", "Sleeve": "Full Sleeve", "Color": "Blue", "Pattern": "Plain", "material": 240, "Quantity": 40},
        ],
    },
    {
        "product": "Fleece Hooded Sweatshirt",
        "hsn": "6110",
        "rate": "2199.00",
        "cost": "910.00",
        "gst": "12%",
        "skus": [
            {"Fabric": "Cotton", "Sleeve": "Full Sleeve", "Color": "Black", "Pattern": "Plain", "material": 320, "Quantity": 38},
            {"Fabric": "Cotton", "Sleeve": "Full Sleeve", "Color": "Blue", "Pattern": "Printed", "material": 320, "Quantity": 30},
        ],
    },
    {
        "product": "Washed Denim Jacket",
        "hsn": "6201",
        "rate": "2999.00",
        "cost": "1240.00",
        "gst": "12%",
        "skus": [
            {"Fabric": "Lycra", "Sleeve": "Full Sleeve", "Color": "Blue", "Pattern": "Plain", "material": 340, "Quantity": 26},
        ],
    },
]

# A second intake of stock that already sells: same SKUs, separate entries, so
# the Product -> Entry -> SKU hierarchy has something real to show.
RESTOCK = [
    {
        "product": "Classic Crew Neck T-Shirt",
        "skus": [
            {"Fabric": "Cotton", "Sleeve": "Half Sleeve", "Color": "Black", "Pattern": "Plain", "material": 180, "Quantity": 80},
        ],
    },
    {
        "product": "Oxford Casual Shirt",
        "skus": [
            {"Fabric": "Cotton", "Sleeve": "Full Sleeve", "Color": "Blue", "Pattern": "Checked", "material": 160, "Quantity": 24},
        ],
    },
]


# The parties an invoice can be drawn between. state_code drives the tax
# split: same state as the seller gives CGST+SGST, a different one gives IGST.
PARTIES = [
    {
        "role": "company", "name": "Be90s Apparel Pvt Ltd",
        "email": "accounts@be90s.example", "phone": "011 4566 2210",
        "address": "Unit 14, Okhla Industrial Estate Phase II\nNew Delhi 110020",
        "state": "Delhi", "state_code": "07",
        "pan": "AAFCB7291K", "gstin": "07AAFCB7291K1ZP",
    },
    {
        "role": "buyer", "name": "Urban Threads Retail LLP",
        "email": "purchase@urbanthreads.example", "phone": "022 2845 1190",
        "address": "Shop 3, Linking Road\nBandra West, Mumbai 400050",
        "state": "Maharashtra", "state_code": "27",
        "pan": "AAEFU4417Q", "gstin": "27AAEFU4417Q1ZD",
    },
    {
        "role": "buyer", "name": "Metro Fashion House",
        "email": "orders@metrofashion.example", "phone": "011 2634 7781",
        "address": "B-42, Lajpat Nagar II\nNew Delhi 110024",
        "state": "Delhi", "state_code": "07",
        "pan": "AADCM9912H", "gstin": "07AADCM9912H1Z8",
    },
    {
        "role": "buyer", "name": "Trendline Stores Pvt Ltd",
        "email": "buying@trendline.example", "phone": "079 4008 3312",
        "address": "412, Iscon Emporio, Satellite\nAhmedabad 380015",
        "state": "Gujarat", "state_code": "24",
        "pan": "AAHCT6620M", "gstin": "24AAHCT6620M1ZR",
    },
]


class Command(BaseCommand):
    help = "Create a realistic apparel catalogue: products, entries, SKUs and barcodes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete existing items, entries, SKUs and barcodes first.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        schema_fields = get_schema().fields
        sku_fields = sku_engine.get_sku_fields(schema_fields)

        if options["flush"]:
            Barcode.objects.all().delete()
            Item.objects.all().delete()
            Entry.objects.all().delete()
            Sku.objects.all().delete()
            SkuNumber.objects.all().delete()
            self.stdout.write(self.style.WARNING("Cleared existing inventory."))

        by_product = {row["product"]: row for row in CATALOGUE}
        created_lines = 0

        for row in CATALOGUE + RESTOCK:
            source = by_product[row["product"]]
            product_data = {
                "Product Name": source["product"],
                "HSN": source["hsn"],
                "Selling Rate": source["rate"],
                "Manufacturing Cost": source["cost"],
                "GST Rate": source["gst"],
                # Variant fields belong to the SKU, not the product row.
                "Fabric": None,
                "Sleeve": None,
                "Color": None,
                "Pattern": None,
                "material": None,
                "Quantity": None,
            }
            lines = _create_entries(product_data, row["skus"], schema_fields, sku_fields)
            created_lines += len(lines)
            self.stdout.write(f"  {source['product']:<30} {', '.join(lines)}")

        # Labels last, once every line exists.
        made = 0
        for entry in Item.objects.select_related("sku", "barcode").order_by("pk"):
            if barcode_engine.build_value(entry) is not None:
                barcode_engine.sync_barcode_for_entry(entry)
                made += 1

        parties = self._seed_parties(options["flush"])
        invoice = self._seed_invoice(parties)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {Entry.objects.count()} entries, {created_lines} lines, "
                f"{Sku.objects.count()} SKUs, {made} barcodes, "
                f"{len(parties)} parties, invoice {invoice.number} ({invoice.total})."
            )
        )

    def _seed_parties(self, flush):
        from invoicing.models import Enterprise

        if flush:
            Enterprise.objects.all().delete()

        made = []
        for row in PARTIES:
            party, _ = Enterprise.objects.get_or_create(
                name=row["name"], defaults={k: v for k, v in row.items() if k != "name"}
            )
            made.append(party)
        return made

    def _seed_invoice(self, parties):
        """One worked invoice, so the sales side is not an empty table.

        Built from the models and then recalculated, so the tax split is the
        engine's own arithmetic rather than numbers written in here. The buyer
        is in Maharashtra against a Delhi seller, which makes it IGST.
        """
        from datetime import date

        from invoicing.models import Invoice, InvoiceLine

        snapshot_fields = ["name", "email", "phone", "address", "state", "state_code", "pan", "gstin"]

        def snapshot(party):
            return {f: getattr(party, f, "") or "" for f in snapshot_fields}

        seller = parties[0]
        buyer = parties[1]

        invoice, created = Invoice.objects.get_or_create(
            number="BE90/26-27/0001",
            defaults={
                "date": date(2026, 9, 24),
                "seller": seller,
                "buyer": buyer,
                "seller_snapshot": snapshot(seller),
                "dispatch_snapshot": snapshot(seller),
                "buyer_snapshot": snapshot(buyer),
                "ship_to_snapshot": snapshot(buyer),
                "reference_no": "PO-4417",
                "po_no": "PO-4417",
                "payment_mode": "NEFT - 30 days",
                "vehicle_no": "DL01AB4417",
            },
        )
        if not created:
            return invoice

        rows = [
            ("Classic Crew Neck T-Shirt (Cotton, Half Sleeve, Black, Plain)", "6109", "COT-HAL-BLA-001", 40, "799.00", "5.00"),
            ("Oxford Casual Shirt (Cotton, Full Sleeve, Blue, Checked)", "6205", "COT-FUL-BLU-004", 12, "1699.00", "12.00"),
            ("Fleece Hooded Sweatshirt (Cotton, Full Sleeve, Black, Plain)", "6110", "COT-FUL-BLA-008", 8, "2199.00", "12.00"),
        ]
        for description, hsn, sku_code, qty, rate, gst in rows:
            InvoiceLine.objects.create(
                invoice=invoice,
                description=description,
                hsn=hsn,
                sku_code=sku_code,
                quantity=qty,
                rate=rate,
                gst_rate=gst,
            )

        invoice.recalculate()
        return invoice
