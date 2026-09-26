"""Invoicing pages: the two masters, and the invoice itself.

The invoice page is one screen split down the middle - entry fields on the
left, a live preview of the printed invoice on the right - and products are
put on it with the barcode scanner rather than typed. Scanning the same label
twice adds one to that line instead of repeating it.
"""

import json
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from items import barcode as barcode_engine

from .gst import in_words, money, split, summarise
from .models import BOTH, COMPANY, Bank, Enterprise, Invoice, InvoiceLine, InvoiceSetting

# The fields every party must carry, whichever side of the invoice it is on.
PARTY_FIELDS = ["name", "email", "phone", "address", "state", "state_code", "pan", "gstin"]


# --------------------------------------------------------------------------
# Enterprise Master
# --------------------------------------------------------------------------


def enterprise_list(request):
    """Every registered party, sellers and buyers alike."""
    role = request.GET.get("role") or ""
    query = (request.GET.get("q") or "").strip()

    enterprises = Enterprise.objects.all()
    if role:
        enterprises = enterprises.filter(role__in=[role, BOTH])
    if query:
        enterprises = enterprises.filter(name__icontains=query)

    return render(
        request,
        "invoicing/enterprise_list.html",
        {"enterprises": enterprises, "role": role, "query": query},
    )


def _read_party(post):
    """Pull the fixed party fields off a posted form."""
    return {field: (post.get(field) or "").strip() for field in PARTY_FIELDS}


def _read_extra(post):
    """The free-form extras: paired ``extra_key``/``extra_value`` inputs."""
    keys = post.getlist("extra_key")
    values = post.getlist("extra_value")
    return {key.strip(): value.strip() for key, value in zip(keys, values) if key.strip()}


def enterprise_add(request):
    if request.method == "POST":
        data = _read_party(request.POST)
        if not data["name"]:
            messages.error(request, "Name is required.")
        else:
            Enterprise.objects.create(
                role=request.POST.get("role") or BOTH,
                extra=_read_extra(request.POST),
                **data,
            )
            messages.success(request, f"{data['name']} registered.")
            return redirect("invoicing:enterprise_list")

    return render(
        request,
        "invoicing/enterprise_form.html",
        {"mode": "add", "posted": request.POST if request.method == "POST" else None},
    )


def enterprise_edit(request, pk):
    enterprise = get_object_or_404(Enterprise, pk=pk)

    if request.method == "POST":
        data = _read_party(request.POST)
        if not data["name"]:
            messages.error(request, "Name is required.")
        else:
            for field, value in data.items():
                setattr(enterprise, field, value)
            enterprise.role = request.POST.get("role") or enterprise.role
            enterprise.extra = _read_extra(request.POST)
            enterprise.save()
            messages.success(request, f"{enterprise.name} updated.")
            return redirect("invoicing:enterprise_list")

    return render(
        request,
        "invoicing/enterprise_form.html",
        {"mode": "edit", "enterprise": enterprise},
    )


def enterprise_delete(request, pk):
    if request.method == "POST":
        enterprise = get_object_or_404(Enterprise, pk=pk)
        name = enterprise.name
        enterprise.delete()
        messages.success(request, f"{name} removed.")
    return redirect("invoicing:enterprise_list")


def enterprise_json(request, pk):
    """One party's details, for the invoice page to fill its fields with."""
    enterprise = get_object_or_404(Enterprise, pk=pk)
    payload = enterprise.as_party()
    payload["id"] = enterprise.pk
    payload["extra"] = enterprise.extra
    payload["union_territory"] = enterprise.is_union_territory
    return JsonResponse(payload)


# --------------------------------------------------------------------------
# Invoice Master
# --------------------------------------------------------------------------


def invoice_master(request):
    """Numbering, declaration, signature and the banks to be paid into."""
    setting = InvoiceSetting.load()

    if request.method == "POST":
        setting.prefix = request.POST.get("prefix", "")
        setting.suffix = request.POST.get("suffix", "")
        setting.auto_increment = request.POST.get("auto_increment") == "on"
        try:
            setting.next_number = max(1, int(request.POST.get("next_number") or 1))
        except ValueError:
            messages.error(request, "Next number must be a whole number.")
            return redirect("invoicing:invoice_master")
        setting.declaration = request.POST.get("declaration", "")
        setting.terms = request.POST.get("terms", "")
        if request.FILES.get("signature"):
            setting.signature = request.FILES["signature"]
        if request.FILES.get("logo"):
            setting.logo = request.FILES["logo"]
        setting.save()
        messages.success(request, "Invoice master updated.")
        return redirect("invoicing:invoice_master")

    return render(
        request,
        "invoicing/invoice_master.html",
        {"setting": setting, "banks": Bank.objects.all()},
    )


def bank_add(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        if not name:
            messages.error(request, "Bank name is required.")
        else:
            Bank.objects.create(
                name=name,
                account_no=(request.POST.get("account_no") or "").strip(),
                ifsc=(request.POST.get("ifsc") or "").strip(),
                branch=(request.POST.get("branch") or "").strip(),
                payment_qr=request.FILES.get("payment_qr"),
            )
            messages.success(request, f"{name} added.")
    return redirect("invoicing:invoice_master")


def bank_delete(request, pk):
    if request.method == "POST":
        bank = get_object_or_404(Bank, pk=pk)
        bank.delete()
        messages.success(request, "Bank removed.")
    return redirect("invoicing:invoice_master")


# --------------------------------------------------------------------------
# Invoicing
# --------------------------------------------------------------------------


def invoice_list(request):
    return render(request, "invoicing/invoice_list.html", {"invoices": Invoice.objects.all()})


def invoice_create(request):
    """The invoice screen: fields on the left, live preview on the right."""
    setting = InvoiceSetting.load()

    if request.method == "POST":
        return _save_invoice(request, setting)

    companies = Enterprise.objects.filter(role__in=[COMPANY, BOTH])
    buyers = Enterprise.objects.exclude(role=COMPANY)

    return render(
        request,
        "invoicing/invoice_create.html",
        {
            "setting": setting,
            "companies": companies,
            "buyers": buyers,
            "banks": Bank.objects.all(),
            "today": date.today().isoformat(),
            "suggested_number": setting.build_number(),
            "party_fields": PARTY_FIELDS,
        },
    )


def _party_from_post(post, prefix):
    """Read one party block (``seller_name``, ``buyer_state_code``, ...)."""
    return {field: (post.get(f"{prefix}_{field}") or "").strip() for field in PARTY_FIELDS}


def _lines_from_post(post):
    """The scanned lines, posted as one JSON blob by the page."""
    try:
        rows = json.loads(post.get("lines") or "[]")
    except ValueError:
        return []

    lines = []
    for row in rows:
        description = (row.get("description") or "").strip()
        if not description:
            continue
        lines.append(
            {
                "description": description,
                "hsn": (row.get("hsn") or "").strip(),
                "scanned_code": (row.get("scanned_code") or "").strip(),
                "sku_code": (row.get("sku_code") or "").strip(),
                "quantity": Decimal(str(row.get("quantity") or 1)),
                "unit": (row.get("unit") or "Nos").strip(),
                "rate": Decimal(str(row.get("rate") or 0)),
                "gst_rate": Decimal(str(row.get("gst_rate") or 0)),
            }
        )
    return lines


def _save_invoice(request, setting):
    seller = _party_from_post(request.POST, "seller")
    buyer = _party_from_post(request.POST, "buyer")
    dispatch = _party_from_post(request.POST, "dispatch")
    ship_to = _party_from_post(request.POST, "ship")
    lines = _lines_from_post(request.POST)

    errors = []
    if not seller["name"]:
        errors.append("Choose the company the invoice is raised by.")
    if not buyer["name"]:
        errors.append("Choose the buyer.")
    if not lines:
        errors.append("Scan at least one product onto the invoice.")

    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect("invoicing:invoice_create")

    # "Same as company" leaves the block blank; fall back rather than print
    # an empty dispatch/shipping panel.
    dispatch = dispatch if dispatch["name"] else dict(seller)
    ship_to = ship_to if ship_to["name"] else dict(buyer)

    invoice = Invoice.objects.create(
        number=(request.POST.get("number") or setting.build_number()).strip(),
        date=request.POST.get("date") or date.today(),
        seller_id=request.POST.get("seller_id") or None,
        buyer_id=request.POST.get("buyer_id") or None,
        seller_snapshot=seller,
        dispatch_snapshot=dispatch,
        buyer_snapshot=buyer,
        ship_to_snapshot=ship_to,
        reference_no=(request.POST.get("reference_no") or "").strip(),
        reference_date=request.POST.get("reference_date") or None,
        po_no=(request.POST.get("po_no") or "").strip(),
        po_date=request.POST.get("po_date") or None,
        vehicle_no=(request.POST.get("vehicle_no") or "").strip(),
        payment_mode=(request.POST.get("payment_mode") or "").strip(),
        bank_id=request.POST.get("bank") or None,
        note=(request.POST.get("note") or "").strip(),
    )
    for line in lines:
        InvoiceLine.objects.create(invoice=invoice, **line)
    invoice.recalculate()

    if setting.auto_increment:
        setting.next_number += 1
        setting.save(update_fields=["next_number"])

    messages.success(request, f"Invoice {invoice.number} saved - {invoice.total} total.")
    return redirect("invoicing:invoice_detail", pk=invoice.pk)


def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice.objects.prefetch_related("lines"), pk=pk)
    seller_code = invoice.seller_snapshot.get("state_code")
    buyer_code = invoice.buyer_snapshot.get("state_code")

    lines = list(invoice.lines.all())
    for line in lines:
        # "2.5% CGST 80.93 / 2.5% SGST 80.93" printed inside the line itself.
        line.tax_rows = [
            {"label": label, "percent": percent, "amount": amount}
            for label, percent, amount in split(line.gst_rate, line.amount, seller_code, buyer_code)
        ]
        line.tax_total = money(sum(row["amount"] for row in line.tax_rows))
        line.line_total = money(line.amount + line.tax_total)

    totals = summarise(
        [{"hsn": line.hsn, "taxable": line.amount, "gst_rate": line.gst_rate} for line in lines],
        seller_code,
        buyer_code,
    )
    return render(
        request,
        "invoicing/invoice_detail.html",
        {
            "invoice": invoice,
            "lines": lines,
            "totals": totals,
            "amount_words": in_words(totals["total"]),
            "tax_words": in_words(totals["tax"]),
            "setting": InvoiceSetting.load(),
        },
    )


def invoice_scan(request):
    """What a scanned barcode puts on an invoice.

    Answers with the product as a sales line - name, HSN, rate, GST rate - and
    deliberately not with the stock behind it: how many lots a warehouse holds
    is nobody's business on a customer's invoice.
    """
    value = (request.GET.get("value") or "").strip()
    result = barcode_engine.resolve(value)

    if result is None or not result.get("sku"):
        return JsonResponse({"value": value, "found": False})

    entry = result.get("entry")
    data = entry.data if entry else {}
    sku = result["sku"]

    variant = ", ".join(f"{key}: {val}" for key, val in sku.data.items() if val)
    name = data.get("Product Name") or sku.code

    return JsonResponse(
        {
            "value": value,
            "found": True,
            "description": f"{name} ({variant})" if variant else name,
            "product": name,
            "variant": variant,
            "hsn": str(data.get("HSN") or ""),
            "rate": str(data.get("Selling Rate") or data.get("Rate") or 0),
            "gst_rate": _gst_rate(data.get("GST Rate")),
            "sku_code": sku.code,
            "unit": "Nos",
            "available": str(data.get("Quantity") or ""),
        }
    )


def _gst_rate(value):
    """"5%", "5", 5 -> "5" - the number the tax split is worked out from."""
    text = str(value or "").strip().replace("%", "")
    try:
        return str(Decimal(text or "0"))
    except Exception:
        return "0"


def invoice_preview(request):
    """Totals for the live preview: the same split the saved invoice will use."""
    try:
        payload = json.loads(request.body or "{}")
    except ValueError:
        payload = {}

    lines = []
    for row in payload.get("lines", []):
        quantity = Decimal(str(row.get("quantity") or 0))
        rate = Decimal(str(row.get("rate") or 0))
        lines.append(
            {
                "hsn": row.get("hsn") or "",
                "taxable": money(quantity * rate),
                "gst_rate": Decimal(str(row.get("gst_rate") or 0)),
            }
        )

    seller_code = payload.get("seller_state_code")
    buyer_code = payload.get("buyer_state_code")
    totals = summarise(lines, seller_code, buyer_code)

    line_rows = []
    for row in payload.get("lines", []):
        quantity = Decimal(str(row.get("quantity") or 0))
        rate = Decimal(str(row.get("rate") or 0))
        net = money(quantity * rate)
        components = split(row.get("gst_rate"), net, seller_code, buyer_code)
        tax = money(sum(amount for _, _, amount in components))
        line_rows.append(
            {
                "net": str(net),
                "tax": str(tax),
                "total": str(money(net + tax)),
                "components": [
                    {"label": label, "percent": str(percent), "amount": str(amount)}
                    for label, percent, amount in components
                ],
            }
        )

    return JsonResponse(
        {
            "taxable": str(totals["taxable"]),
            "cgst": str(totals["cgst"]),
            "sgst": str(totals["sgst"]),
            "ugst": str(totals["ugst"]),
            "igst": str(totals["igst"]),
            "tax": str(totals["tax"]),
            "total": str(totals["total"]),
            "intra_state": totals["intra_state"],
            "union_territory": totals["union_territory"],
            "amount_words": in_words(totals["total"]),
            "tax_words": in_words(totals["tax"]),
            "line_rows": line_rows,
            "hsn_rows": [
                {
                    "hsn": row["hsn"],
                    "taxable": str(row["taxable"]),
                    "rate": str(row["rate"]),
                    "tax": str(row["tax"]),
                    "components": [
                        {"label": c["label"], "percent": str(c["percent"]), "amount": str(c["amount"])}
                        for c in row["components"]
                    ],
                }
                for row in totals["hsn_rows"]
            ],
        }
    )
