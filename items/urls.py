from django.urls import path

from . import views

app_name = "items"

urlpatterns = [
    path("", views.item_list, name="list"),
    path("overview/", views.overview, name="overview"),
    path("add/", views.item_add, name="add"),
    path("add-existing/", views.add_existing, name="add_existing"),
    path("<int:pk>/edit/", views.item_edit, name="edit"),
    path("<int:pk>/delete/", views.item_delete, name="delete"),
    path("<int:pk>/barcodes.zip", views.entry_barcodes_zip, name="barcodes_zip"),
    path("<int:pk>/duplicate/", views.item_duplicate, name="duplicate"),
    path("<int:item_pk>/sku/add/", views.sku_add, name="sku_add"),
    path("sku-format/", views.sku_format, name="sku_format"),
    path("barcode/scan/", views.barcode_scan, name="barcode_scan"),
    path("barcode/scan/test/", views.barcode_scan_test, name="barcode_scan_test"),
    path("barcode/lookup/", views.barcode_lookup, name="barcode_lookup"),
]
