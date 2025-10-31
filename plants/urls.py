from django.urls import path
from . import views

app_name = 'plants'

urlpatterns = [
    path("groups/", views.plant_group_list, name="plant_group_list"),
    path("groups/<int:group_id>/", views.plant_list, name="plant_list_by_group"),
    path('', views.plant_list, name='plant_list'),
    path('<int:plant_id>/', views.plant_timeline, name='plant_timeline'),
    path('<int:plant_id>/add-image/', views.add_image, name='add_image'),
    path('create/', views.create_plant, name='create_plant'),
    path('<int:plant_id>/edit/', views.edit_plant, name='edit_plant'),        # ← NEU
    path('<int:plant_id>/delete/', views.delete_plant, name='delete_plant'),  # ← NEU
]