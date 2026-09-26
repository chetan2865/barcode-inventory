# Complete Batch Entry System Implementation

## Overview

The system now supports **multiple separate entries for the same product/SKU**. Each entry is an independent database record representing a warehouse receipt.

```
Product: "demo Nirmal" (Item #16)
├─ Entry 1: ID=214, Qty=10, Cost=₹600, GST=18%, Date=Aug 16
├─ Entry 2: ID=213, Qty=120, Cost=₹600, GST=18%, Date=Aug 16  
└─ Entry 3: ID=212, Qty=120, Cost=₹600, GST=18%, Date=Aug 16

SKU: DEM-FAB-QWE-10-010
├─ Links to Entry 1, 2, 3 (same SKU, different batches)

SKU: DEM-FAB-ABC-10-011
└─ Links to its own separate entries
```

## Backend Structure

### Database Model (items/models.py)
```python
class BatchEntry(models.Model):
    item = ForeignKey(Item)           # Product
    sku = ForeignKey(Sku)             # Variant
    batch_number = CharField()        # Unique batch ID
    quantity = PositiveIntegerField() # Units received
    cost_price = DecimalField()       # Per-unit cost
    gst_slab = CharField()            # Tax rate (18%, 5%, etc)
    entry_date = DateField()          # When received
    notes = TextField()               # Supplier/location notes
    created_at = DateTimeField()      # Auto timestamp
    updated_at = DateTimeField()      # Auto timestamp
```

### Admin Interface
- **Dedicated BatchEntryAdmin**: Full CRUD + filtering + search
- **Inline BatchEntryInline**: Edit batches directly from Item/SKU pages
- All changes fully visible in Django admin

### Frontend Views
1. **batch_entries_list()** - Display all entries
   - Search by batch number, SKU code, product name
   - Filter by GST slab or entry date
   - Paginated (50 per page)
   - Shows: ID, Batch Number, Product, SKU, Qty, Cost, GST, Entry Date, Timestamps

2. **batch_entry_add()** - Create new entry
   - Select product (Item)
   - Select SKU variant
   - Fill batch details (number, qty, cost, GST, date, notes)
   - Form validation

3. **batch_entry_edit()** - Update existing entry
   - Can change quantity, cost, GST, date, notes
   - Cannot change product/SKU (maintains link integrity)

4. **batch_entry_delete()** - Remove entry
   - Confirmation dialog to prevent accidental deletion
   - Only deletes this entry, not product or SKU

## Frontend Structure

### URLs (items/urls.py)
```
/batch-entries/                    # List all entries
/batch-entries/add/                # Add new entry
/batch-entries/<id>/edit/          # Edit entry
/batch-entries/<id>/delete/        # Delete entry (POST)
```

### Templates

#### batch_entries_list.html
Shows all batch entries in a table:
- Columns: ID, Batch Number, Product, SKU Code, Quantity, Cost Price, GST, Entry Date, Created At, Actions
- Search bar (batch number, SKU, product name)
- GST filter dropdown
- Pagination
- Edit/Delete buttons per row

#### batch_entry_form.html
Form for adding/editing entries:
- Product dropdown (disabled on edit)
- SKU dropdown (disabled on edit)
- Batch Number input
- Quantity input (number)
- Cost Price input (decimal)
- GST Slab input
- Entry Date picker
- Notes textarea
- Form validation (required fields, numeric validation)

#### list.html (Updated)
Item list now shows:
- Column: "Quantity (All Variants)" - total qty across all entries
- Column: "SKUs" - count of unique SKUs
- Column: "Batch Entries" - count of entries for this product (clickable)
- New "+ Entry" button in Actions to quickly add entry from item list
- Updated "View SKUs" button

#### base.html (Updated)
Navigation bar includes:
- Link to "Batch Entries" list page

## How to Use

### Scenario: Receive same product multiple times with different costs

**Step 1: Product already exists**
- Go to Items → Item Display
- Find "demo Nirmal" product

**Step 2: Add first batch entry**
- Click "+ Entry" button in Actions
- OR go to Batch Entries → Add Entry
- Select: Product, SKU variant
- Fill: Batch Number (e.g., "BATCH-2024-001")
- Fill: Quantity (e.g., 100)
- Fill: Cost Price (e.g., ₹600)
- Fill: GST Slab (e.g., "18%")
- Leave Entry Date blank (uses today) or set manually
- Add Notes (optional, e.g., "Supplier ABC")
- Click "Create Batch Entry"
- **Database: NEW ROW created** with ID 214

**Step 3: Add second batch entry (same product/SKU, different price)**
- Go to Batch Entries → Add Entry
- Select: Same Product, Same SKU
- Fill: Batch Number (e.g., "BATCH-2024-002")
- Fill: Quantity (e.g., 50)
- Fill: Cost Price (e.g., ₹650) ← **Different cost!**
- Fill: GST Slab (e.g., "18%")
- Click "Create Batch Entry"
- **Database: NEW ROW created** with ID 213

**Step 4: View all entries**
- Go to Batch Entries
- See both entries listed separately
- Each has own ID, cost, quantity, date
- Click "Quantity (All Variants)" on Items list to see total

### Editing an Entry
- Batch Entries → Find entry → Edit
- Can update: Quantity, Cost Price, GST, Entry Date, Notes
- Cannot change: Product or SKU (maintains data integrity)
- Click "Update Batch Entry"

### Deleting an Entry
- Batch Entries → Find entry → Delete button
- Confirm deletion
- Only this entry deleted, not product or SKU

## Key Features

✅ **Each Entry = Separate Row**
- New entry always creates new database record
- Doesn't update or replace existing entries
- Full audit trail with timestamps

✅ **Independent Pricing**
- Each entry can have different cost per unit
- Tracks price changes over time
- Historical cost record

✅ **Independent GST**
- Each entry can have different tax rate
- Handles GST law changes
- Different states/slabs tracked

✅ **Independent Dates**
- When each batch was received
- Supports backdating if needed
- Useful for delayed data entry

✅ **Search & Filter**
- Find entries by batch number
- Find entries by SKU code
- Find entries by product name
- Filter by GST rate
- Filter by entry date

✅ **Admin Integration**
- Also manageable via Django admin
- Inline editing from Items/SKUs
- Bulk operations support

✅ **Data Integrity**
- Cannot orphan entries (product/SKU must exist)
- Timestamp tracking (created_at, updated_at)
- Batch number indexed for fast lookup

## Admin Management

### Via Django Admin

**Items Page:**
- Shows "BATCH ENTRIES" count in list
- Inline section to add entries directly
- All entries visible under the item

**SKUs Page:**
- Shows "BATCH RECEIPTS" count in list
- Inline section to add entries
- All entries for this SKU visible

**Batch Entries Page:**
- Full CRUD operations
- List all entries with filters
- Search by batch number
- Edit any entry
- Delete entries

## Technical Details

### Database
- Migration: `items/migrations/0008_batchentry.py`
- Table: `items_batchentry`
- Foreign keys to both Item and Sku (referential integrity)

### Relationships
```
BatchEntry
├── item (FK) → Item (many-to-one)
└── sku (FK) → Sku (many-to-one)
```

### Ordering
Entries ordered by:
1. Entry date (newest first)
2. Created timestamp (newest first)

### Indexes
- batch_number - for fast search
- entry_date - for filtering
- created_at - for sorting

## URL Paths

**Frontend URLs:**
- `/items/batch-entries/` - List all
- `/items/batch-entries/add/` - Add form
- `/items/batch-entries/<id>/edit/` - Edit form
- `/items/batch-entries/<id>/delete/` - Delete (POST)

**From Items List:**
- Click "+ Entry" button → goes to `/items/batch-entries/add/?item=<id>`
- Pre-selects the product

**From Item Detail (Admin):**
- Inline "Add another Batch Entry" button in BatchEntryInline
- Direct database creation

## Example Data Flow

```
User Action → Django View → Database → Template → Display

1. User clicks "+ Entry" on Item #16
   → batch_entry_add() view
   → User fills form
   → Validation checks
   → BatchEntry.objects.create()
   → NEW ROW in database
   → Redirect to batch_entries_list
   → Shows entry in table with ID

2. User edits entry ID 214
   → batch_entry_edit(pk=214)
   → Gets form with current values
   → User changes quantity from 10 to 15
   → Validation checks
   → entry.quantity = 15, entry.save()
   → Database updated (same row)
   → Redirect to batch_entries_list
   → Shows updated entry

3. User views Batch Entries list
   → batch_entries_list() view
   → Queries all BatchEntry records
   → Sorts by -entry_date, -created_at
   → Enriches with product names
   → Paginates (50 per page)
   → Renders batch_entries_list.html
   → Shows table with all entries
```

## Common Tasks

### How to check total quantity of a product?
- Go to Items → Item Display
- Look at "Quantity (All Variants)" column
- Shows sum of all entries' quantities

### How to see all batches of one SKU?
- Go to Batch Entries
- Search for SKU code (e.g., "DEM-FAB-QWE-10-010")
- All entries for that SKU shown

### How to find entries by cost range?
- Not yet in filters, but can:
  - Go to Batch Entries
  - View all entries
  - Sort/filter manually
  - (Could add cost range filter in future)

### How to export entries?
- Admin panel → Batch Entries
- Select entries → Export to CSV (if django-import-export installed)
- Or copy from table to spreadsheet

### How to track entry history?
- Each entry has created_at and updated_at
- View in Batch Entries list: "Created At" column
- Admin shows full timestamp history

---

## Summary

The new batch entry system is **production-ready** and handles:
- ✅ Multiple entries per product/SKU
- ✅ Independent costs per entry
- ✅ Independent GST per entry
- ✅ Full CRUD operations
- ✅ Search and filtering
- ✅ Admin integration
- ✅ Frontend web interface
- ✅ Data integrity and audit trail
