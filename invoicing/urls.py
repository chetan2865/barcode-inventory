from django.urls import path

from . import views

app_name = "invoicing"

urlpatterns = [
    # Enterprise Master - the parties an invoice is drawn between.
    path("enterprises/", views.enterprise_list, name="enterprise_list"),
    path("enterprises/add/", views.enterprise_add, name="enterprise_add"),
    path("enterprises/<int:pk>/edit/", views.enterprise_edit, name="enterprise_edit"),
    path("enterprises/<int:pk>/delete/", views.enterprise_delete, name="enterprise_delete"),
    path("enterprises/<int:pk>/json/", views.enterprise_json, name="enterprise_json"),
    # Invoice Master - banks, declaration, signature, numbering.
    path("invoice-master/", views.invoice_master, name="invoice_master"),
    path("invoice-master/bank/add/", views.bank_add, name="bank_add"),
    path("invoice-master/bank/<int:pk>/delete/", views.bank_delete, name="bank_delete"),
    # Invoicing itself.
    path("invoices/", views.invoice_list, name="invoice_list"),
    path("invoices/new/", views.invoice_create, name="invoice_create"),
    path("invoices/<int:pk>/", views.invoice_detail, name="invoice_detail"),
    path("invoices/scan/", views.invoice_scan, name="invoice_scan"),
    path("invoices/preview/", views.invoice_preview, name="invoice_preview"),
]
