from django import template

from core.object_types import label as object_type_label_lookup
from items.forms import column_class

register = template.Library()


@register.filter
def object_type_label(code):
    return object_type_label_lookup(code)


@register.filter
def col_class(field):
    return column_class(field)


@register.filter
def get_item(data, key):
    return (data or {}).get(key)


@register.filter
def input_value(posted, index):
    """Re-populate ``field_<index>`` from a re-rendered POST on validation error."""
    if not posted:
        return ""
    return posted.get(f"field_{index}", "")


@register.simple_tag
def input_name(index):
    return f"field_{index}"


@register.simple_tag
def field_value(field, index, posted, item):
    if posted:
        return posted.get(f"field_{index}", "")
    if item:
        return item.data.get(field.get("name"), "")
    return ""


@register.filter
def number_step(decimal_places):
    if not decimal_places:
        return "1"
    return "0." + ("0" * (int(decimal_places) - 1)) + "1"


@register.simple_tag
def field_checked(field, index, posted, item):
    if posted:
        return posted.get(f"field_{index}") == "on"
    if item:
        return bool(item.data.get(field.get("name")))
    return False
