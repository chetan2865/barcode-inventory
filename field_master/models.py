from django.db import models


class MasterSchema(models.Model):
    """Persists the Master JSON for a single page.

    This project is JSON-first. The Master JSON is the single source of truth
    and this model exists only to store it. We do NOT normalise every field
    property into its own table/column. The whole page structure lives inside
    the ``fields`` JSON list, in display order.
    """

    page = models.CharField(max_length=200, unique=True, default="Item Registration")
    fields = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.page

    def master_json(self):
        """Return the complete Master JSON for this page."""
        return {
            "page": self.page,
            "fields": self.fields,
        }
