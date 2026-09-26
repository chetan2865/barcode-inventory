"""Central Object Type registry for the Inventory Management System.

Every major entity in the system eventually gets a stable two-digit Object
Type code (used, among other things, as the first field of every barcode
payload). This is the single place those codes are defined - nothing else
in the project should hardcode them.

The project does not use every code yet; they exist now so future modules
(Vendor, Customer, Warehouse, Purchase, Sales, BOM, Stock, ...) have a
stable code to build on.
"""

SKU = "01"
ITEM = "02"
VENDOR = "03"
CUSTOMER = "04"
WAREHOUSE = "05"
PURCHASE = "06"
SALES = "07"
BOM = "08"
STOCK = "09"
BARCODE = "10"

OBJECT_TYPES = {
    SKU: "SKU",
    ITEM: "Item",
    VENDOR: "Vendor",
    CUSTOMER: "Customer",
    WAREHOUSE: "Warehouse",
    PURCHASE: "Purchase",
    SALES: "Sales",
    BOM: "BOM",
    STOCK: "Stock",
    BARCODE: "Barcode",
}

CHOICES = list(OBJECT_TYPES.items())


def label(code):
    """Human-readable name for an Object Type code."""
    return OBJECT_TYPES.get(code, code)
