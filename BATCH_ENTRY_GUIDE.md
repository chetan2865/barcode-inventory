# Batch Entry System - Quick Guide

## Overview
The new **BatchEntry** model allows you to track multiple warehouse receipts of the **same product/SKU** with different costs, GST slabs, quantities, and dates. This is perfect for handling batches of cloth or other items arriving at different times.

## How It Works

### Before (Old System)
- One `Item` = One Product Record
- Multiple intakes of the same item weren't tracked separately
- Cost and GST couldn't change per batch

### After (New System)
- One `Item` = Product Master (e.g., "Blue Cotton T-Shirt")
- One `SKU` = Variant (e.g., "COT-BLU-M-001")
- **Multiple `BatchEntry` rows** = Multiple warehouse receipts of the same SKU with different details

```
Item: "Blue Cotton T-Shirt"
├── SKU: COT-BLU-M-001
│   ├── BatchEntry #1: Qty=100, Cost=₹600, GST=18%, Date=2024-01-15
│   ├── BatchEntry #2: Qty=50, Cost=₹650, GST=18%, Date=2024-02-10
│   └── BatchEntry #3: Qty=200, Cost=₹580, GST=12%, Date=2024-03-05
```

## Where to Add Batch Entries

### Option 1: From the Items List (Fastest)
1. Go to **Django Admin → Items**
2. Click on a Product to open it
3. Scroll down to **Batch Entries** inline section
4. Click **Add another Batch Entry**
5. Fill in:
   - **Batch Number**: Unique identifier (e.g., "BATCH-2024-001", "LOT-B123")
   - **Quantity**: Number of units received
   - **Cost Price**: Cost per unit (₹)
   - **GST Slab**: Tax rate (e.g., "18%", "5%", "IGST-18%")
   - **Entry Date**: When batch was received (auto-filled with today)
   - **Notes**: Any additional info (supplier, warehouse location, etc.)
6. Select the **SKU** for this batch
7. Click **Save**

### Option 2: From the SKUs List
1. Go to **Django Admin → SKUs**
2. Click on a SKU (e.g., "COT-BLU-M-001")
3. Scroll down to **Batch Entries** inline section
4. Add batch details same as Option 1

### Option 3: Dedicated Batch Entries Page
1. Go to **Django Admin → Batch Entries**
2. Click **Add Batch Entry**
3. Fill in all fields:
   - Select **Product (Item)**
   - Select **SKU** (must exist first)
   - Fill Batch Number, Quantity, Cost, GST, Entry Date, Notes
4. Click **Save**

## Key Fields

| Field | Purpose | Example |
|-------|---------|---------|
| **Batch Number** | Unique batch/lot ID | BATCH-2024-001, LOT-B123 |
| **Quantity** | Units received in this batch | 100, 50, 200 |
| **Cost Price** | Per-unit cost | 600, 650, 580 |
| **GST Slab** | Tax rate for this batch | 18%, 5%, IGST-18% |
| **Entry Date** | Date received | 2024-01-15 |
| **Notes** | Extra info | "From supplier X", "Warehouse A" |

## Features

✅ **Track multiple receipts** of the same product/SKU  
✅ **Different costs** for each batch (handles price changes)  
✅ **Different GST slabs** (new tax rules, state-wise GST, etc.)  
✅ **Separate quantities** (don't mix old and new stock)  
✅ **Timestamp tracking** (knows when each batch was added)  
✅ **Searchable** (filter by batch number, date, GST rate)  
✅ **Admin dashboard** (see all batch entries at a glance)

## Admin Dashboard Views

### Batch Entries List
Shows all batches across the entire system:
- **Columns**: Batch Number, Product, SKU Code, Quantity, Cost, GST, Entry Date
- **Filters**: By entry date, GST slab, creation date
- **Search**: By batch number, SKU code, or product name

### Item Detail Page
- **Tab**: "Batch Entries" inline shows all batches for this product
- **Add**: Quick add new batches directly from product page

### SKU Detail Page
- **Tab**: "Batch Entries" inline shows all batches for this variant
- **Add**: Quick add new batches directly from SKU page

## Workflow Example

**Scenario**: You receive cloth batches at different times with different costs

### Step 1: Create Product (if not exists)
- Go to Items → Add Item
- Fill product name, color, size, etc.
- Save

### Step 2: Create SKU (if not exists)
- Go to Items → Select Product
- Click "Add another SKU Variant"
- Fill variant fields (Color, Size, etc.)
- Save

### Step 3: Add Batch #1 (First Receipt)
- Go to Items → Select Product
- Scroll to Batch Entries → Add
- Batch Number: `BATCH-2024-001`
- Quantity: `100`
- Cost Price: `₹600`
- GST Slab: `18%`
- Entry Date: `2024-01-15`
- Notes: `From ABC Supplier`
- SKU: Select the variant
- Save

### Step 4: Add Batch #2 (Later Receipt - Same SKU)
- Go to Items → Select Product → Batch Entries
- Add another batch:
- Batch Number: `BATCH-2024-002`
- Quantity: `50`
- Cost Price: `₹650` ← Different cost!
- GST Slab: `18%`
- Entry Date: `2024-02-10`
- Notes: `From ABC Supplier, new pricing`
- SKU: Same variant
- Save

✅ **Now you have 2 separate stock entries for the same SKU with different costs!**

## Notes & Best Practices

- **Batch Numbers** should be unique or at least meaningful (include date, supplier, etc.)
- **Cost Price** is per-unit, so total cost = Cost Price × Quantity
- **GST Slab** can be a simple percentage (18%) or detailed (IGST-18%, CGST-9%, SGST-9%)
- **Entry Date** auto-fills with today but you can change it if backdating
- **Multiple SKUs per Item**: Each SKU variant can have multiple batches
- **Delete Safety**: Deleting a batch entry only removes that batch, not the product or SKU

## Questions?

- **How do I update stock quantities?** Edit the Batch Entry and change the Quantity field
- **Can I track sales from batches?** Not yet - future feature could link sales to batch entries (FIFO/LIFO)
- **Can I merge batches?** Create new batch entry and delete old ones (or use notes to track merges)
- **Can I prevent duplicate batch numbers?** Yes - uncomment `unique_together` in BatchEntry model to enforce unique batch numbers per SKU
