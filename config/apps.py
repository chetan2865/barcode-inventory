from django.contrib.admin.apps import AdminConfig


class InventoryAdminConfig(AdminConfig):
    """Swaps in the section-grouped admin index (see config.admin)."""

    default_site = "config.admin.InventoryAdminSite"
