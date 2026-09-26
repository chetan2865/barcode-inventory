from django.contrib import admin

from .models import Bank, Enterprise, Invoice, InvoiceLine, InvoiceSetting


@admin.register(Enterprise)
class EnterpriseAdmin(admin.ModelAdmin):
    """Enterprise Master: the parties invoices are drawn between."""

    list_display = ("name", "role", "gstin", "state", "state_code", "phone")
    list_filter = ("role", "state")
    search_fields = ("name", "gstin", "pan")


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    """Issued invoices. Party blocks are snapshots, so they never change."""

    list_display = ("number", "date", "buyer_name", "taxable", "cgst", "sgst", "ugst", "igst", "total")
    search_fields = ("number",)
    inlines = [InvoiceLineInline]

    @admin.display(description="Buyer")
    def buyer_name(self, obj):
        return obj.buyer_snapshot.get("name") or "-"


admin.site.register(Bank)
admin.site.register(InvoiceSetting)
