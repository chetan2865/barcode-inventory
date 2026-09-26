import json

from django.contrib import messages
from django.shortcuts import redirect, render

from .builder import FIELD_SIZES, FIELD_TYPES, SKU_TRANSFORMS, build_field
from .models import MasterSchema

PAGE_NAME = "Item Registration"


def get_schema():
    """Return the single Master JSON row for the Item Registration page."""
    schema, _ = MasterSchema.objects.get_or_create(page=PAGE_NAME)
    return schema


# Fields with no explicit sku_config.order sort after those that have one.
_NO_ORDER = 10_000


def _sku_sequence(fields):
    """Fields marked "Include in SKU", ordered by their ``sku_config.order``.

    Mirrors ``items.sku.get_sku_fields`` locally so field_master doesn't need
    to import the items app just to render the SKU Variant Sequence preview.
    """
    sku_fields = [f for f in fields if f.get("include_in_sku")]

    def sort_key(field):
        order = (field.get("sku_config") or {}).get("order")
        return order if isinstance(order, int) else _NO_ORDER

    return sorted(sku_fields, key=sort_key)


def field_list(request):
    """List every field currently in the Master JSON, in order."""
    schema = get_schema()
    context = {
        "schema": schema,
        "fields": schema.fields,
        "sku_sequence": _sku_sequence(schema.fields),
        "master_json_pretty": json.dumps(schema.master_json(), indent=4),
    }
    return render(request, "field_master/list.html", context)


def field_add(request):
    """Field designer: build ONE field and append it to the Master JSON."""
    if request.method == "POST":
        schema = get_schema()
        field = build_field(request.POST)

        if not field["name"]:
            messages.error(request, "Field Name is required.")
            return render(
                request,
                "field_master/form.html",
                {
                    "field": field,
                    "field_types": FIELD_TYPES,
                    "field_sizes": FIELD_SIZES,
                    "sku_transforms": SKU_TRANSFORMS,
                    "mode": "add",
                },
            )

        # Append the new field's JSON object, then regenerate/save Master JSON.
        fields = list(schema.fields)
        fields.append(field)
        schema.fields = fields
        schema.save()

        messages.success(request, f"Field \"{field['name']}\" added.")
        return redirect("field_master:list")

    return render(
        request,
        "field_master/form.html",
        {
            "field": None,
            "field_types": FIELD_TYPES,
            "field_sizes": FIELD_SIZES,
            "mode": "add",
        },
    )


def field_edit(request, index):
    """Edit ONE field's JSON object, then regenerate the Master JSON.

    System fields (Product Name, HSN, ...) can't be edited at all. Every
    other field keeps its original ``name`` forever: once created, a field
    can never be renamed. A field already saved with "Include in SKU" can't
    have that turned off either, since doing so is effectively removing it
    from the SKU configuration.
    """
    schema = get_schema()
    fields = list(schema.fields)

    if index < 0 or index >= len(fields):
        messages.error(request, "That field does not exist.")
        return redirect("field_master:list")

    existing = fields[index]

    if existing.get("system"):
        messages.error(request, f"\"{existing.get('name')}\" is a system field and cannot be modified.")
        return redirect("field_master:list")

    if request.method == "POST":
        field = build_field(request.POST)

        if not field["name"]:
            messages.error(request, "Field Name is required.")
            return render(
                request,
                "field_master/form.html",
                {
                    "field": field,
                    "index": index,
                    "field_types": FIELD_TYPES,
                    "field_sizes": FIELD_SIZES,
                    "sku_transforms": SKU_TRANSFORMS,
                    "mode": "edit",
                },
            )

        # Renaming is never allowed once a field exists.
        field["name"] = existing["name"]
        # A field already included in SKU composition can't be pulled back out.
        if existing.get("include_in_sku"):
            field["include_in_sku"] = True
            if not field.get("sku_config"):
                field["sku_config"] = existing.get("sku_config", {})

        fields[index] = field
        schema.fields = fields
        schema.save()

        messages.success(request, f"Field \"{field['name']}\" updated.")
        return redirect("field_master:list")

    return render(
        request,
        "field_master/form.html",
        {
            "field": fields[index],
            "index": index,
            "field_types": FIELD_TYPES,
            "field_sizes": FIELD_SIZES,
            "sku_transforms": SKU_TRANSFORMS,
            "mode": "edit",
        },
    )


def field_delete(request, index):
    """Remove ONE field's JSON object from the Master JSON.

    System fields can never be deleted. Fields already included in the SKU
    configuration can't be deleted either, since removing one would silently
    change how every future SKU is composed.
    """
    if request.method == "POST":
        schema = get_schema()
        fields = list(schema.fields)
        if 0 <= index < len(fields):
            target = fields[index]
            if target.get("system"):
                messages.error(request, f"\"{target.get('name')}\" is a system field and cannot be deleted.")
            elif target.get("include_in_sku"):
                messages.error(
                    request,
                    f"\"{target.get('name')}\" is part of the SKU configuration and cannot be removed.",
                )
            else:
                fields.pop(index)
                schema.fields = fields
                schema.save()
                messages.success(request, f"Field \"{target.get('name', '')}\" deleted.")
        else:
            messages.error(request, "That field does not exist.")
    return redirect("field_master:list")


def field_move(request, index, direction):
    """Move a field up or down inside the Master JSON, keeping list order."""
    if request.method == "POST":
        schema = get_schema()
        fields = list(schema.fields)

        target = index - 1 if direction == "up" else index + 1

        if 0 <= index < len(fields) and 0 <= target < len(fields):
            fields[index], fields[target] = fields[target], fields[index]
            schema.fields = fields
            schema.save()
        else:
            messages.error(request, "Cannot move that field.")
    return redirect("field_master:list")
