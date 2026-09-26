"""Custom admin site that regroups the index into business sections.

Django's admin index groups models by the app they live in (``items``,
``field_master``, ...). This project reads better split by role instead:

* **Detail** - the two tables that hold the actual business records:
  Products (``items.Item``) and SKUs (``items.Sku``).
* **Fields** - every other table: the supporting/config tables (barcodes,
  SKU format, SKU sequences, the field-master schema).

Only the index grouping changes; each model's own admin pages, permissions and
URLs are untouched.
"""

from django.contrib import admin

# Models shown in the "Detail" section, in this order, as
# ("<app_label>.<model_name>", "<label to show>").
DETAIL_MODELS = [
    ("items.item", "Products"),
    ("items.sku", "SKUs"),
    ("items.entry", "Entries"),
    ("invoicing.invoice", "Invoices"),
    ("invoicing.enterprise", "Enterprises"),
]

DETAIL_SECTION = "Detail"
FIELDS_SECTION = "Fields"

# Apps left in their own section rather than folded into "Fields"
# (Django's built-in user/group admin).
UNGROUPED_APPS = {"auth"}


class InventoryAdminSite(admin.AdminSite):
    site_header = "Inventory Administration"
    site_title = "Inventory Admin"
    index_title = "Tables"

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)

        # Per-app pages (/admin/items/) keep Django's normal grouping.
        if app_label is not None:
            return app_list

        detail_order = {key: i for i, (key, _) in enumerate(DETAIL_MODELS)}
        detail_labels = dict(DETAIL_MODELS)

        detail_models = []
        field_models = []
        untouched = []

        for app in app_list:
            if app["app_label"] in UNGROUPED_APPS:
                untouched.append(app)
                continue

            for model in app["models"]:
                key = f"{app['app_label']}.{model['object_name'].lower()}"
                if key in detail_order:
                    model = {**model, "name": detail_labels[key], "_order": detail_order[key]}
                    detail_models.append(model)
                else:
                    field_models.append(model)

        sections = []
        if detail_models:
            detail_models.sort(key=lambda m: m.pop("_order"))
            sections.append(self._section(DETAIL_SECTION, detail_models))
        if field_models:
            field_models.sort(key=lambda m: m["name"])
            sections.append(self._section(FIELDS_SECTION, field_models))

        return sections + untouched

    @staticmethod
    def _section(name, models):
        """One index section. ``app_label`` is a display-only slug: these
        sections are not real apps, so the section header is not a link."""
        return {
            "name": name,
            "app_label": name.lower(),
            "app_url": "",
            "has_module_perms": True,
            "models": models,
        }
