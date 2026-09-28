import base64
import io
import json
import re
import zipfile

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import models
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from field_master.views import get_schema

from . import barcode as barcode_engine
from . import quantity as quantity_engine
from . import sku as sku_engine
from .forms import input_name, parse_item_data, registration_schema, visible_fields
from .models import TRANSFORM_CHOICES, Entry, Item, Sku, SkuFormat


def _schema_fields():
    return get_schema().fields


def sku_format(request):
    """Edit the global SKU-format defaults (separator, length, padding, ...)."""
    fmt = SkuFormat.load()

    if request.method == "POST":
        # Separator is always "-" and SKUs are always uppercase - not user
        # editable. SkuFormat.save() enforces this even if bypassed here.
        try:
            fmt.component_length = max(1, int(request.POST.get("component_length") or 3))
            fmt.sequence_padding = max(1, int(request.POST.get("sequence_padding") or 3))
        except ValueError:
            messages.error(request, "Length and padding must be whole numbers.")
            return redirect("items:sku_format")
        transform = request.POST.get("transform")
        fmt.transform = transform if transform in dict(TRANSFORM_CHOICES) else fmt.transform
        fmt.save()
        messages.success(request, "SKU format updated.")
        return redirect("items:sku_format")

    return render(
        request,
        "items/sku_format.html",
        {"fmt": fmt, "transforms": TRANSFORM_CHOICES},
    )


def item_list(request):
    """Item Display: product -> its entries -> the SKUs of each entry.

    Three folds. The top row is the product name. Inside it sit that product's
    entries - one per press of Save - each showing the product detail it was
    saved with and how many SKUs it carries. Opening an entry reveals those
    SKUs with their quantities and barcodes.

    The Entry grouping is display only: quantities, codes and barcodes all
    still come from the Item rows underneath.

    Supports a free-text search (``q``) across every field's value, plus an
    optional single-field filter (``filter_field`` / ``filter_value``), both
    applied in Python since lines live in a JSONField with a dynamic schema.
    """
    schema_fields = _schema_fields()
    fields = visible_fields(registration_schema(schema_fields))
    sku_fields = sku_engine.get_sku_fields(schema_fields)
    product_field = _product_field_name(registration_schema(schema_fields))

    # Inside a product, its name is the group heading - no point repeating it.
    detail_fields = [field for field in fields if field["name"] != product_field]

    query = (request.GET.get("q") or "").strip()
    filter_field = request.GET.get("filter_field") or ""
    filter_value = (request.GET.get("filter_value") or "").strip()

    lines = list(
        Item.objects.order_by("-created_at").select_related("sku", "barcode", "entry")
    )

    def matches(line):
        if query:
            haystack = " ".join(str(v) for v in line.data.values() if v is not None)
            if line.sku:
                haystack += " " + line.sku.code
            if query.lower() not in haystack.lower():
                return False
        if filter_field and filter_value:
            value = str(line.data.get(filter_field, "") or "")
            if filter_value.lower() not in value.lower():
                return False
        return True

    if query or (filter_field and filter_value):
        lines = [line for line in lines if matches(line)]

    for line in lines:
        line.json_pretty = json.dumps(quantity_engine.entry_json(line), indent=4, default=str)
        line.quantity = quantity_engine.entry_quantity(line, schema_fields)
        # What is actually left: intake less sales, plus anything returned.
        line.available = quantity_engine.available_quantity(line, schema_fields)
        line.sold = quantity_engine.sold_quantity(line)

    # Group lines by their entry, then entries by product name. Both keep the
    # newest-first order the lines arrived in.
    entries = []
    seen = {}
    for line in lines:
        key = line.entry_id or f"line-{line.pk}"
        group = seen.get(key)
        if group is None:
            group = {
                "entry": line.entry,
                "pk": line.entry_id or line.pk,
                "product": (line.entry.product if line.entry else None)
                or line.data.get(product_field)
                or "(unnamed)",
                "data": line.entry.data if line.entry else line.data,
                "created_at": line.entry.created_at if line.entry else line.created_at,
                "lines": [],
            }
            seen[key] = group
            entries.append(group)
        group["lines"].append(line)

    products = []
    by_name = {}
    for group in entries:
        bucket = by_name.get(group["product"])
        if bucket is None:
            bucket = {"name": group["product"], "entries": []}
            by_name[group["product"]] = bucket
            products.append(bucket)
        bucket["entries"].append(group)

    paginator = Paginator(products, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "items/list.html",
        {
            "fields": fields,
            "detail_fields": detail_fields,
            "products": page_obj,
            "page_obj": page_obj,
            "product_field": product_field,
            "sku_fields": sku_fields,
            "sku_form_fields": sku_engine.sku_form_fields(schema_fields),
            "qty_name": quantity_engine.quantity_field_name(schema_fields),
            "query": query,
            "filter_field": filter_field,
            "filter_value": filter_value,
        },
    )


def item_add(request):
    """Add New Product: product fields typed in by hand, plus its SKUs.

    Same shape as Add Existing Product, except nothing is pre-filled - this is
    a product the system has not seen before, so the name is typed rather than
    chosen. SKUs are optional here: registering the product alone is allowed,
    and SKUs can be added to it later.

    Reached from the scan panel with ``?scanned=<value>`` when a code came back
    unknown, this becomes the "register this new material" form: exactly one
    SKU, and the scanned code is kept on the line so scanning that same outside
    barcode again finds it.
    """
    schema_fields = _schema_fields()
    fields = registration_schema(schema_fields)
    sku_fields = sku_engine.get_sku_fields(schema_fields)
    form_fields = sku_engine.sku_form_fields(schema_fields)

    scanned_code = (request.POST.get("scanned_code") or request.GET.get("scanned") or "").strip()
    single_sku = bool(scanned_code)

    if request.method == "POST":
        product_data, errors = parse_item_data(fields, request.POST, request.FILES)
        parsed, block_errors = _parse_sku_blocks(request.POST, request.FILES, form_fields)
        errors.extend(block_errors)

        if scanned_code:
            # One scan, one material, one SKU - however many blocks were posted.
            parsed = parsed[:1]
            if not parsed:
                errors.append("Add the SKU for this scanned material before saving.")
            product_data[barcode_engine.SOURCE_CODE_KEY] = scanned_code

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            created = _create_entries(product_data, parsed, schema_fields, sku_fields)
            if created:
                messages.success(
                    request,
                    f"Saved {len(created)} entr{'y' if len(created) == 1 else 'ies'}: {', '.join(created)}."
                    + (f" Scanning {scanned_code} now finds it." if scanned_code else ""),
                )
            else:
                entry = Entry.objects.create(
                    product=product_data.get(_product_field_name(fields)) or "",
                    data=dict(product_data),
                )
                Item.objects.create(data=product_data, entry=entry)
                messages.success(request, "Product registered. Add SKUs to it whenever you are ready.")
            return redirect("items:list")

    return render(
        request,
        "items/add_new.html",
        {
            "fields": fields,
            "sku_fields": sku_fields,
            "sku_form_fields": form_fields,
            "qty_name": quantity_engine.quantity_field_name(schema_fields),
            "posted": request.POST if request.method == "POST" else None,
            "scanned_code": scanned_code,
            "single_sku": single_sku,
        },
    )


def _parse_sku_blocks(post, files, form_fields):
    """Parse every posted SKU block. Returns ``(parsed, errors)``."""
    parsed, errors = [], []
    for index, values in _sku_blocks(post, form_fields):
        data, block_errors = parse_item_data(form_fields, values, files)
        errors.extend(f"SKU {index + 1}: {message}" for message in block_errors)
        parsed.append(data)
    return parsed, errors


def _create_entries(product_data, parsed_blocks, schema_fields, sku_fields):
    """Save one Entry for this press of Save, with one line per SKU.

    The lines are Item rows exactly as before - each carries its own quantity
    and its own barcode, and nothing merges. The Entry above them only records
    that these lines were saved together, so the display can show a product,
    its entries, and each entry's SKUs.
    """
    qty_name = quantity_engine.quantity_field_name(schema_fields)
    created = []

    entry = Entry.objects.create(
        product=product_data.get(_product_field_name(registration_schema(schema_fields))) or "",
        data=dict(product_data),
    )

    for submitted in parsed_blocks:
        identity = {field["name"]: submitted.get(field["name"]) for field in sku_fields}
        sku = sku_engine.find_matching_sku(sku_fields, identity)
        if sku is None:
            sku = Sku.objects.create(
                data=identity,
                code=sku_engine.generate_sku(schema_fields, identity),
            )
        line = Item(data=dict(product_data), sku=sku, entry=entry)
        quantity_engine.set_quantity(line, submitted.get(qty_name), schema_fields, save=False)
        line.save()
        created.append(f"#{line.pk} {sku.code}")

    return created


def add_existing(request):
    """Add Existing Product: one page for product + as many SKUs as needed.

    The product is chosen from the ones already registered and its fields come
    back filled in but editable, because a new intake of the same product can
    carry a different cost, date or GST. Every SKU row on the page saves as
    its own entry, so their quantities stay separate.
    """
    schema_fields = _schema_fields()
    fields = registration_schema(schema_fields)
    sku_fields = sku_engine.get_sku_fields(schema_fields)
    form_fields = sku_engine.sku_form_fields(schema_fields)
    product_field = _product_field_name(fields)

    # One option per distinct product name, carrying that product's own values.
    known = {}
    for item in Item.objects.order_by("-created_at"):
        name = item.data.get(product_field)
        if name and name not in known:
            known[name] = {k: v for k, v in item.data.items()}
    products = [{"name": name} for name in known]

    if request.method == "POST":
        product_data, errors = parse_item_data(fields, request.POST, request.FILES)
        parsed, block_errors = _parse_sku_blocks(request.POST, request.FILES, form_fields)
        errors.extend(block_errors)

        if not parsed:
            errors.append("Add at least one SKU before saving.")

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            created = _create_entries(product_data, parsed, schema_fields, sku_fields)
            messages.success(
                request,
                f"Saved {len(created)} entr{'y' if len(created) == 1 else 'ies'}: {', '.join(created)}.",
            )
            return redirect("items:list")

    return render(
        request,
        "items/add_existing.html",
        {
            "fields": fields,
            "sku_fields": sku_fields,
            "sku_form_fields": form_fields,
            "products": products,
            "products_json": json.dumps(known, default=str),
            "product_field": product_field,
            "qty_name": quantity_engine.quantity_field_name(schema_fields),
        },
    )


def _product_field_name(fields):
    """The field that names the product - the first visible one."""
    for field in fields:
        if field.get("hide"):
            continue
        if field["name"].strip().lower() in {"product name", "item name"}:
            return field["name"]
    for field in fields:
        if not field.get("hide"):
            return field["name"]
    return ""


def _sku_blocks(post, form_fields):
    """Group ``sku_<block>_field_<n>`` inputs back into per-SKU dicts.

    Blocks left completely blank (the trailing empty one the page always keeps
    ready) are dropped rather than saved as empty entries.
    """
    names = [input_name(index) for index in range(len(form_fields))]
    indices = sorted({int(match.group(1)) for match in (re.match(r"sku_(\d+)_field_\d+$", key) for key in post) if match})

    blocks = []
    for index in indices:
        values = {name: (post.get(f"sku_{index}_{name}") or "") for name in names}
        if any(str(value).strip() for value in values.values()):
            blocks.append((len(blocks), values))
    return blocks


def item_edit(request, pk):
    item = get_object_or_404(Item, pk=pk)
    schema_fields = registration_schema(_schema_fields())
    fields = schema_fields

    if request.method == "POST":
        data, errors = parse_item_data(schema_fields, request.POST, request.FILES, existing_data=item.data)
        if errors:
            for error in errors:
                messages.error(request, error)
            return render(
                request,
                "items/registration_form.html",
                {"fields": fields, "mode": "edit", "item": item, "posted": request.POST},
            )

        item.data = data
        item.save()
        messages.success(request, "Item updated.")
        return redirect("items:list")

    return render(
        request,
        "items/registration_form.html",
        {"fields": fields, "mode": "edit", "item": item},
    )


def item_delete(request, pk):
    if request.method == "POST":
        item = get_object_or_404(Item, pk=pk)
        item.delete()
        messages.success(request, "Item deleted.")
    return redirect("items:list")


def item_duplicate(request, pk):
    """Create a new Item entry as a duplicate of an existing item.
    
    The new entry gets a fresh ID and timestamp but same data.
    """
    if request.method == "POST":
        source_item = get_object_or_404(Item, pk=pk)
        
        # A fresh intake: same product data, but its own SKU and its own
        # quantity, set when a SKU is added to it. Nothing is copied that
        # would merge this entry with the one it came from.
        new_item = Item.objects.create(data=dict(source_item.data))
        
        messages.success(request, f"New entry #{new_item.pk} created from item #{pk}.")
    
    return redirect("items:list")


def sku_add(request, item_pk):
    """Add one SKU variant to an Item, from the Item Display page itself.

    If the submitted detail (Fabric/Sleeve/Color/...) exactly matches an
    existing Sku, that Sku is reused - its code and sequence number never
    change just because another product asked for the same combo. Only a
    genuinely new combination of values mints a new sequence number.
    """
    if request.method == "POST":
        item = get_object_or_404(Item, pk=item_pk)
        schema_fields = _schema_fields()
        sku_fields = sku_engine.get_sku_fields(schema_fields)

        if not sku_fields:
            messages.error(request, 'No fields are marked "Include in SKU" yet.')
            return redirect("items:list")

        form_fields = sku_engine.sku_form_fields(schema_fields)
        submitted, errors = parse_item_data(form_fields, request.POST, request.FILES)
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            # Split identity from stock: only the identity half is ever matched
            # on, code-generated from, or written to Sku.data.
            data = {field["name"]: submitted.get(field["name"]) for field in sku_fields}
            qty_name = quantity_engine.quantity_field_name(schema_fields)
            qty = quantity_engine.to_number(submitted.get(qty_name))

            existing = sku_engine.find_matching_sku(sku_fields, data)
            if existing:
                sku = existing
                verb = "Reused existing SKU"
            else:
                code = sku_engine.generate_sku(schema_fields, data)
                sku = Sku.objects.create(data=data, code=code)
                verb = "SKU generated:"

            # One entry holds one SKU. If this entry already has one, the new
            # intake becomes its own entry row instead of merging into it -
            # quantities of separate entries are never added together.
            if item.sku_id is None:
                entry = item
            else:
                entry = Item(data=dict(item.data))

            entry.sku = sku
            quantity_engine.set_quantity(entry, qty, schema_fields, save=False)
            entry.save()

            messages.success(
                request,
                f"{verb} {sku.code} - entry #{entry.pk} with quantity {qty}.",
            )

    return redirect("items:list")


def barcode_scan(request):
    """Barcode Scan page: resolve a scanned entry label back to its entry.

    Each entry carries its own barcode (``<sku code>-<entry id>``), so a scan
    identifies one intake exactly - its own quantity and cost. The other
    entries sharing the same SKU are listed underneath for context, never
    merged into it.
    """
    scanned_value = request.GET.get("value", "").strip()
    result = None
    entries = []
    entry_fields = []

    if scanned_value:
        result = barcode_engine.resolve(scanned_value)
        if result is None:
            messages.error(request, f'No record found for barcode "{scanned_value}".')
        elif result["sku"]:
            entries = quantity_engine.sku_entries(result["sku"])
            entry_fields = visible_fields(registration_schema(_schema_fields()))

    return render(
        request,
        "items/barcode_scan.html",
        {
            "scanned_value": scanned_value,
            "result": result,
            "entries": entries,
            "entry_fields": entry_fields,
            "qty_name": quantity_engine.quantity_field_name(_schema_fields()),
        },
    )


# A lot of 50,000 pieces would render 50,000 PNGs and stall the request, so
# downloads above this are refused rather than silently truncated.
MAX_UNIT_LABELS = 1000


def entry_barcodes_zip(request, pk):
    """Download every label for one lot as a single ZIP.

    Inside: the lot barcode that goes on the box, plus one unit barcode per
    piece (``...-1`` ... ``...-<quantity>``) for the items themselves.
    """
    entry = get_object_or_404(Item.objects.select_related("sku", "barcode"), pk=pk)

    lot_value = barcode_engine.build_value(entry)
    if lot_value is None:
        messages.error(request, f"Entry #{entry.pk} has no SKU yet, so it has no barcode.")
        return redirect("items:list")

    units = barcode_engine.unit_count(entry)
    if units > MAX_UNIT_LABELS:
        messages.error(
            request,
            f"Entry #{entry.pk} holds {units} pieces - more than the {MAX_UNIT_LABELS} "
            "labels one download can render.",
        )
        return redirect("items:list")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        # The parent label, for the outer packaging of the lot.
        filename, content = barcode_engine.generate_image(lot_value)
        archive.writestr(f"lot/{filename}", content.read())

        # One label per piece inside the lot.
        for number in range(1, units + 1):
            value = barcode_engine.unit_value(entry, number)
            filename, content = barcode_engine.generate_image(value)
            archive.writestr(f"units/{filename}", content.read())

        archive.writestr(
            "README.txt",
            "\n".join(
                [
                    f"Entry #{entry.pk}",
                    f"Product : {entry.data.get('Product Name', '')}",
                    f"SKU     : {entry.sku.code}",
                    f"Quantity: {units}",
                    "",
                    f"lot/   - 1 barcode for the box: {lot_value}",
                    f"units/ - {units} barcodes for the pieces: "
                    f"{lot_value}-1 .. {lot_value}-{units}",
                    "",
                ]
            ),
        )

    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{lot_value}-labels.zip"'
    return response


def barcode_scan_test(request):
    """Scanner Test page: a live bench for USB barcode readers.

    A USB reader is a HID keyboard - it "types" the code and (usually) sends
    Enter. This page listens for that at the document level, so no input needs
    focus, and shows every scan with its timing so a reader can be checked
    without touching the real scan flow.
    """
    return render(request, "items/barcode_scan_test.html", {})


def barcode_lookup(request):
    """JSON lookup for one scanned value, used by the Scanner Test page."""
    value = request.GET.get("value", "").strip()
    result = barcode_engine.resolve(value)

    if result is None:
        return JsonResponse({"value": value, "found": False})

    sku = result["sku"]
    entry = result["entry"]
    siblings = [
        {
            "item_id": other.pk,
            "product": other.data.get("Product Name") or f"Entry #{other.pk}",
            "quantity": quantity_engine.entry_quantity(other),
            "created": other.created_at.strftime("%Y-%m-%d"),
            "scanned": entry is not None and other.pk == entry.pk,
        }
        for other in (quantity_engine.sku_entries(sku) if sku else [])
    ]

    return JsonResponse(
        {
            "value": value,
            "found": True,
            "object_type": result["object_type"],
            "object_id": result["object_id"],
            "entry_id": result["entry_id"],
            "quantity": result["quantity"],
            "unit": result["unit"],
            "unit_in_range": result["unit_in_range"],
            "source_code": result["source_code"],
            "scanned_source": bool(result["source_scan"]),
            "product": entry.data.get("Product Name") if entry else None,
            "sku_id": result["sku_id"],
            "sku_code": sku.code if sku else None,
            "sku_data": sku.data if sku else {},
            "entries": siblings,
        }
    )


def overview(request):
    """Operational summary of what is already in the database.

    Read-only: every number here is counted or summed from existing rows, and
    the quantity total goes through the same ``quantity_engine`` the Item
    Display page uses, so it can never disagree with it.
    """
    from invoicing.models import BOTH, COMPANY, BUYER, Enterprise, Invoice

    schema_fields = _schema_fields()
    product_field = _product_field_name(registration_schema(schema_fields))

    lines = list(Item.objects.select_related("sku", "entry").order_by("-created_at"))

    # Products are a grouping of entries by name, exactly as on Item Display.
    product_names = []
    seen_names = set()
    total_quantity = 0
    for line in lines:
        name = (line.entry.product if line.entry else None) or line.data.get(product_field) or "(unnamed)"
        if name not in seen_names:
            seen_names.add(name)
            product_names.append(name)
        total_quantity += quantity_engine.to_number(
            quantity_engine.entry_quantity(line, schema_fields)
        ) or 0

    invoices = Invoice.objects.order_by("-created_at")
    invoice_total = invoices.aggregate(models.Sum("total"))["total__sum"] or 0

    recent_entries = []
    for line in lines[:8]:
        recent_entries.append({
            "pk": line.pk,
            "product": (line.entry.product if line.entry else None)
                       or line.data.get(product_field) or "(unnamed)",
            "sku": line.sku.code if line.sku else "",
            "quantity": quantity_engine.entry_quantity(line, schema_fields),
            "created_at": line.created_at,
        })

    return render(
        request,
        "items/overview.html",
        {
            "product_count": len(product_names),
            "entry_count": len(lines),
            "sku_count": Sku.objects.count(),
            "total_quantity": total_quantity,
            "qty_name": quantity_engine.quantity_field_name(schema_fields),
            "invoice_count": invoices.count(),
            "invoice_total": invoice_total,
            # Matches Enterprise Master: a "both" party counts on each side.
            "company_count": Enterprise.objects.filter(role__in=[COMPANY, BOTH]).count(),
            "buyer_count": Enterprise.objects.filter(role__in=[BUYER, BOTH]).count(),
            "field_count": len(schema_fields),
            "recent_entries": recent_entries,
            "recent_invoices": invoices[:6],
        },
    )


def entry_labels(request, pk):
    """Print-ready hang tags for one entry.

    One tag per piece, each carrying that piece's own unit barcode
    (``<sku>-<entry>-<n>``), so two garments of the same lot never share a
    label. Barcodes are rendered inline as data URIs rather than written to
    MEDIA_ROOT: nothing is stored, so this works with or without a volume.

    ``?copies=N`` overrides how many tags are laid out, for a short reprint.
    """
    entry = get_object_or_404(Item.objects.select_related("sku", "barcode"), pk=pk)

    lot_value = barcode_engine.build_value(entry)
    if lot_value is None:
        messages.error(request, f"Entry #{entry.pk} has no SKU yet, so it has no label.")
        return redirect("items:list")

    try:
        copies = int(request.GET.get("copies") or 0)
    except ValueError:
        copies = 0
    if copies <= 0:
        copies = barcode_engine.unit_count(entry) or 1
    copies = min(copies, MAX_UNIT_LABELS)

    schema_fields = _schema_fields()
    product_field = _product_field_name(registration_schema(schema_fields))

    # The brand line: the registered seller, falling back to the product name.
    from invoicing.models import BOTH, COMPANY, Enterprise

    company = Enterprise.objects.filter(role__in=[COMPANY, BOTH]).order_by("pk").first()
    brand = company.name if company else (entry.data.get(product_field) or "")

    # Variant attributes, exactly as the schema defines them - no hardcoded
    # Size/Colour, since the field set is user-defined.
    detail_rows = [
        (name, value)
        for name, value in (entry.sku.data or {}).items()
        if str(value or "").strip()
    ]

    tags = []
    for number in range(1, copies + 1):
        value = barcode_engine.unit_value(entry, number) or lot_value
        _, content = barcode_engine.generate_image(value)
        tags.append({
            "value": value,
            "number": number,
            "image": base64.b64encode(content.read()).decode("ascii"),
        })

    return render(
        request,
        "items/labels.html",
        {
            "entry": entry,
            "brand": brand,
            "product": entry.data.get(product_field) or "",
            "style_no": entry.sku.code,
            "detail_rows": detail_rows,
            # The system price field is called "Selling Rate" on some schemas and
            # "Rate" on others (see field_master migration 0003), so accept either -
            # the same fallback invoicing.views uses when pricing an invoice line.
            "mrp": entry.data.get("Selling Rate") or entry.data.get("Rate") or "",
            "hsn": entry.data.get("HSN") or "",
            "tags": tags,
            "copies": copies,
            "quantity": barcode_engine.unit_count(entry),
        },
    )


def returns(request):
    """Take stock back in: scan the label, say how many came back.

    A return is posted as a positive movement against the exact entry the
    barcode identifies, so the goods go back onto the lot they were sold from
    rather than onto a pooled total. Nothing is edited in place - the intake
    figure stays as it was and the return stands beside it in the history.
    """
    from .models import StockMovement

    schema_fields = _schema_fields()
    qty_name = quantity_engine.quantity_field_name(schema_fields)

    scanned_value = (request.GET.get("value") or request.POST.get("value") or "").strip()
    entry = None
    result = None

    if scanned_value:
        result = barcode_engine.resolve(scanned_value)
        entry = (result or {}).get("entry")
        if entry is None:
            messages.error(request, f'No entry found for barcode "{scanned_value}".')

    if request.method == "POST" and entry is not None:
        try:
            amount = Decimal(str(request.POST.get("quantity") or "0"))
        except (InvalidOperation, ValueError):
            amount = Decimal("0")

        sold = quantity_engine.sold_quantity(entry)
        returned = quantity_engine.returned_quantity(entry)
        outstanding = sold - returned

        if amount <= 0:
            messages.error(request, "Enter how many pieces came back.")
        elif amount > outstanding:
            # Returning more than ever went out would invent stock.
            messages.error(
                request,
                f"Only {outstanding:g} piece(s) of entry #{entry.pk} are out on invoices - "
                f"cannot take {amount:g} back.",
            )
        else:
            StockMovement.objects.create(
                entry=entry,
                kind=StockMovement.RETURN,
                quantity=amount,
                note=(request.POST.get("note") or "").strip(),
            )
            messages.success(
                request,
                f"Took back {amount:g} of {entry.sku.code if entry.sku else 'entry'} "
                f"#{entry.pk}. Available is now "
                f"{quantity_engine.available_quantity(entry, schema_fields):g}.",
            )
            return redirect(f"{reverse('items:returns')}?value={scanned_value}")

    context = {
        "scanned_value": scanned_value,
        "entry": entry,
        "result": result,
        "qty_name": qty_name,
        "recent": StockMovement.objects.select_related("entry", "entry__sku")[:12],
    }

    if entry is not None:
        context.update({
            "intake": quantity_engine.entry_quantity(entry, schema_fields),
            "sold": quantity_engine.sold_quantity(entry),
            "returned": quantity_engine.returned_quantity(entry),
            "available": quantity_engine.available_quantity(entry, schema_fields),
            "outstanding": quantity_engine.sold_quantity(entry) - quantity_engine.returned_quantity(entry),
            "history": entry.movements.select_related("invoice")[:20],
        })

    return render(request, "items/returns.html", context)
