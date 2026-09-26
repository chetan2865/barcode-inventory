from django.contrib import admin

from .models import MasterSchema


@admin.register(MasterSchema)
class MasterSchemaAdmin(admin.ModelAdmin):
    list_display = ("page", "updated_at")
    readonly_fields = ("created_at", "updated_at")
