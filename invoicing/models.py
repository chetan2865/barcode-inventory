"""Invoicing: the parties, the settings behind an invoice, and invoices.

Two masters feed the invoice page:

* **Enterprise Master** - every party, whether it is one of our own companies
  or a buyer. The fields an invoice must legally print (name, address, state,
  state code, PAN, GSTIN, phone, email) are columns here; anything else a user
  wants to keep lives in ``extra``.
* **Invoice Master** - the things that surround an invoice rather than belong
  to it: the banks payment can be made to, the declaration, the signature.

An invoice then only has to point at those and record what was sold.
"""

from django.db import models

from .gst import is_union_territory, money, normalise_code

COMPANY = "company"
BUYER = "buyer"
BOTH = "both"

ROLE_CHOICES = [
    (COMPANY, "Our company (seller)"),
    (BUYER, "Buyer"),
    (BOTH, "Both"),
]


class Enterprise(models.Model):
    """One party on an invoice - a company of ours, or a buyer.

    ``state_code`` is what decides the tax split (see invoicing.gst), so it is
    a column of its own rather than something buried in an address line.
    """

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=BUYER)
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    state = models.CharField(max_length=80, blank=True)
    state_code = models.CharField(max_length=4, blank=True)
    pan = models.CharField(max_length=20, blank=True)
    gstin = models.CharField(max_length=20, blank=True)

    # Anything beyond the fixed set - added per enterprise, not per schema.
    extra = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.state_code = normalise_code(self.state_code)
        super().save(*args, **kwargs)

    @property
    def is_union_territory(self):
        return is_union_territory(self.state_code)

    def as_party(self):
        """The party block an invoice prints, and stores a copy of."""
        return {
            "name": self.name,
            "address": self.address,
            "state": self.state,
            "state_code": self.state_code,
            "gstin": self.gstin,
            "pan": self.pan,
            "phone": self.phone,
            "email": self.email,
        }


class Bank(models.Model):
    """A bank account payment can be made to - the invoice's Select Bank list."""

    name = models.CharField(max_length=120)
    account_no = models.CharField(max_length=40, blank=True)
    ifsc = models.CharField(max_length=20, blank=True)
    branch = models.CharField(max_length=120, blank=True)
    payment_qr = models.ImageField(upload_to="invoicing/qr/", blank=True, null=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class InvoiceSetting(models.Model):
    """Invoice Master: one row, holding what every invoice carries alike."""

    prefix = models.CharField(max_length=20, blank=True, default="")
    suffix = models.CharField(max_length=20, blank=True, default="")
    next_number = models.PositiveIntegerField(default=1)
    auto_increment = models.BooleanField(default=True)
    declaration = models.TextField(
        blank=True,
        default=(
            "We declare that this invoice shows the actual price of the goods "
            "described and that all particulars are true and correct."
        ),
    )
    terms = models.TextField(blank=True)
    signature = models.ImageField(upload_to="invoicing/signature/", blank=True, null=True)
    logo = models.ImageField(upload_to="invoicing/logo/", blank=True, null=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Invoice master"
        verbose_name_plural = "Invoice master"

    def __str__(self):
        return "Invoice Master"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def build_number(self, number=None):
        number = self.next_number if number is None else number
        return f"{self.prefix}{number:02d}{self.suffix}"


class Invoice(models.Model):
    """One tax invoice.

    Both party blocks are copied in at save time (``seller_snapshot`` and the
    rest): an invoice is a legal record of what was printed, so editing an
    enterprise later must never rewrite an invoice already issued.
    """

    number = models.CharField(max_length=40)
    date = models.DateField()

    seller = models.ForeignKey(Enterprise, related_name="sales", null=True, on_delete=models.SET_NULL)
    buyer = models.ForeignKey(Enterprise, related_name="purchases", null=True, on_delete=models.SET_NULL)

    seller_snapshot = models.JSONField(default=dict, blank=True)
    dispatch_snapshot = models.JSONField(default=dict, blank=True)
    buyer_snapshot = models.JSONField(default=dict, blank=True)
    ship_to_snapshot = models.JSONField(default=dict, blank=True)

    reference_no = models.CharField(max_length=60, blank=True)
    reference_date = models.DateField(null=True, blank=True)
    po_no = models.CharField(max_length=60, blank=True)
    po_date = models.DateField(null=True, blank=True)
    vehicle_no = models.CharField(max_length=40, blank=True)
    payment_mode = models.CharField(max_length=60, blank=True)
    bank = models.ForeignKey(Bank, null=True, blank=True, on_delete=models.SET_NULL)
    note = models.TextField(blank=True)

    taxable = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cgst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sgst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ugst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    igst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Invoice {self.number}"

    @property
    def place_of_supply(self):
        return self.buyer_snapshot.get("state") or ""

    def recalculate(self, save=True):
        """Re-add the lines and re-split the tax from the stored parties."""
        from .gst import summarise

        rows = [
            {"hsn": line.hsn, "taxable": line.amount, "gst_rate": line.gst_rate}
            for line in self.lines.all()
        ]
        totals = summarise(
            rows,
            self.seller_snapshot.get("state_code"),
            self.buyer_snapshot.get("state_code"),
        )
        self.taxable = totals["taxable"]
        self.cgst = totals["cgst"]
        self.sgst = totals["sgst"]
        self.ugst = totals["ugst"]
        self.igst = totals["igst"]
        self.total = totals["total"]
        if save:
            self.save(update_fields=["taxable", "cgst", "sgst", "ugst", "igst", "total"])
        return totals


class InvoiceLine(models.Model):
    """One product line, usually put there by scanning its barcode.

    ``scanned_code`` is what was scanned, so scanning the same label again
    finds this line and adds one to the quantity instead of repeating it.
    """

    invoice = models.ForeignKey(Invoice, related_name="lines", on_delete=models.CASCADE)

    description = models.CharField(max_length=300)
    hsn = models.CharField(max_length=20, blank=True)
    scanned_code = models.CharField(max_length=128, blank=True, db_index=True)
    sku_code = models.CharField(max_length=120, blank=True)

    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit = models.CharField(max_length=20, blank=True, default="Nos")
    rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        ordering = ("pk",)

    def __str__(self):
        return f"{self.description} x {self.quantity}"

    @property
    def amount(self):
        return money(self.quantity * self.rate)
