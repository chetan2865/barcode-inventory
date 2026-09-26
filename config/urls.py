"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

# The packaged desktop build has no staff area: the inventory pages are the
# whole application there, so /admin/ is simply not routed.
SHOW_ADMIN = not getattr(settings, "DESKTOP_APP", False)

urlpatterns = [
    *([path('admin/', admin.site.urls)] if SHOW_ADMIN else []),
    # Inventory > Masters > Field Master
    path('inventory/masters/field-master/', include('field_master.urls')),
    # Inventory > Items (registration, display, SKU creation)
    path('inventory/items/', include('items.urls')),
    # Sales > Invoicing (enterprise master, invoice master, invoice creation)
    path('sales/', include('invoicing.urls')),
    path('', RedirectView.as_view(pattern_name='field_master:list', permanent=False)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
