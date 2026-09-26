"""How tax is split on an invoice line.

One rule decides everything: whether the supply stays inside the place of
supply or crosses it.

* Same state  -> the rate is halved into CGST + SGST (5% becomes 2.5 + 2.5).
* Union territory (same UT) -> halved into CGST + UGST, which is the same
  arithmetic under a different name.
* Different state -> the whole rate is IGST (5% stays 5%).

The state code on each party is what decides it - two digits, as printed on
every GSTIN - so a typed state name never changes the tax.
"""

from decimal import ROUND_HALF_UP, Decimal

# The union territories that levy UGST instead of SGST, by GST state code.
UNION_TERRITORY_CODES = {
    "04",  # Chandigarh
    "07",  # Delhi
    "25",  # Daman & Diu / Dadra & Nagar Haveli
    "26",  # Dadra & Nagar Haveli and Daman & Diu
    "31",  # Lakshadweep
    "34",  # Puducherry
    "35",  # Andaman & Nicobar Islands
    "38",  # Ladakh
    "97",  # Other territory
}

CGST = "CGST"
SGST = "SGST"
UGST = "UGST"
IGST = "IGST"


def money(value):
    """Round to paise, the way an invoice total has to add up."""
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def normalise_code(state_code):
    """State codes are two digits; accept 4, '4', '04' and mean the same."""
    text = str(state_code or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(2) if digits else ""


def is_union_territory(state_code):
    return normalise_code(state_code) in UNION_TERRITORY_CODES


def is_intra_state(seller_code, buyer_code):
    """True when supply stays within one state or union territory."""
    seller = normalise_code(seller_code)
    buyer = normalise_code(buyer_code)
    return bool(seller) and seller == buyer


def split(rate, taxable, seller_code, buyer_code):
    """Split ``taxable`` at ``rate``% into the components that apply.

    Returns a list of ``(label, percent, amount)``, so a line can print
    "CGST 2.5% 80.03 / SGST 2.5% 80.03" or "IGST 5% 160.06" from one call.
    """
    rate = Decimal(str(rate or 0))
    taxable = Decimal(str(taxable or 0))

    if rate <= 0 or taxable <= 0:
        return []

    if is_intra_state(seller_code, buyer_code):
        half = rate / 2
        amount = money(taxable * half / 100)
        state_label = UGST if is_union_territory(seller_code) else SGST
        return [(CGST, half, amount), (state_label, half, amount)]

    return [(IGST, rate, money(taxable * rate / 100))]


def line_tax(rate, taxable, seller_code, buyer_code):
    """Total tax on one line - the split added back up."""
    return money(sum(amount for _, _, amount in split(rate, taxable, seller_code, buyer_code)))


def summarise(lines, seller_code, buyer_code):
    """Totals for a whole invoice, plus the HSN-wise table printed under it.

    ``lines`` are dicts with ``hsn``, ``taxable`` and ``gst_rate``.
    """
    by_hsn = {}
    totals = {CGST: Decimal("0.00"), SGST: Decimal("0.00"), UGST: Decimal("0.00"), IGST: Decimal("0.00")}
    taxable_total = Decimal("0.00")

    for line in lines:
        taxable = money(line.get("taxable"))
        rate = Decimal(str(line.get("gst_rate") or 0))
        hsn = str(line.get("hsn") or "").strip() or "-"

        taxable_total += taxable
        row = by_hsn.setdefault(
            hsn,
            {"hsn": hsn, "taxable": Decimal("0.00"), "rate": rate, "components": {}, "tax": Decimal("0.00")},
        )
        row["taxable"] += taxable

        for label, percent, amount in split(rate, taxable, seller_code, buyer_code):
            totals[label] += amount
            row["tax"] += amount
            component = row["components"].setdefault(label, {"label": label, "percent": percent, "amount": Decimal("0.00")})
            component["amount"] += amount

    tax_total = money(sum(totals.values()))
    return {
        "intra_state": is_intra_state(seller_code, buyer_code),
        "union_territory": is_union_territory(seller_code) and is_intra_state(seller_code, buyer_code),
        "taxable": money(taxable_total),
        "cgst": money(totals[CGST]),
        "sgst": money(totals[SGST]),
        "ugst": money(totals[UGST]),
        "igst": money(totals[IGST]),
        "tax": tax_total,
        "total": money(taxable_total + tax_total),
        "hsn_rows": [
            {
                "hsn": row["hsn"],
                "taxable": money(row["taxable"]),
                "rate": row["rate"],
                "components": sorted(row["components"].values(), key=lambda c: c["label"]),
                "tax": money(row["tax"]),
            }
            for row in by_hsn.values()
        ],
    }


_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
    "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
    "Eighteen", "Nineteen",
]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _below_thousand(number):
    if number < 20:
        return _ONES[number]
    if number < 100:
        return (_TENS[number // 10] + (" " + _ONES[number % 10] if number % 10 else "")).strip()
    return (_ONES[number // 100] + " Hundred" + (" " + _below_thousand(number % 100) if number % 100 else "")).strip()


def in_words(amount):
    """Indian-format amount in words, as every tax invoice prints it."""
    amount = money(amount)
    rupees = int(amount)
    paise = int((amount - rupees) * 100)

    if rupees == 0:
        words = "Zero"
    else:
        parts = []
        for divisor, name in ((10_000_000, "Crore"), (100_000, "Lakh"), (1_000, "Thousand")):
            if rupees >= divisor:
                parts.append(f"{_below_thousand(rupees // divisor)} {name}")
                rupees %= divisor
        if rupees:
            parts.append(_below_thousand(rupees))
        words = " ".join(parts)

    text = f"{words} Rupees"
    if paise:
        text += f" and {_below_thousand(paise)} Paise"
    return text + " Only"
