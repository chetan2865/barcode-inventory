from django.urls import path

from . import views

app_name = "field_master"

urlpatterns = [
    path("", views.field_list, name="list"),
    path("add/", views.field_add, name="add"),
    path("<int:index>/edit/", views.field_edit, name="edit"),
    path("<int:index>/delete/", views.field_delete, name="delete"),
    path("<int:index>/move/<str:direction>/", views.field_move, name="move"),
    path("<int:index>/hide/", views.field_toggle_hide, name="toggle_hide"),
]
