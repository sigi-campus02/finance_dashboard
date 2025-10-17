from django.urls import path
from billa import views
from billa.api import stats

app_name = 'billa'

urlpatterns = [

    path('', views.billa_dashboard, name='billa_dashboard'),
    path('import/', views.billa_import_upload, name='billa_import'),

    # Einkäufe
    path('einkauefe/', views.billa_einkauefe_liste, name='billa_einkauefe_liste'),
    path('einkauf/<int:einkauf_id>/', views.billa_einkauf_detail, name='billa_einkauf_detail'),

    # Produkte
    path('produkte/', views.billa_produkte_liste, name='billa_produkte_liste'),
    path('produkt/<int:produkt_id>/', views.billa_produkt_detail, name='billa_produkt_detail'),

    # Überkategorien
    path('ueberkategorien/', views.billa_ueberkategorien_liste, name='billa_ueberkategorien_liste'),
    path('ueberkategorie/<str:ueberkategorie>/', views.billa_ueberkategorie_detail, name='billa_ueberkategorie_detail'),

    # Produktgruppen
    path('produktgruppen/', views.billa_produktgruppen_liste, name='billa_produktgruppen_liste'),
    path('produktgruppe/<str:produktgruppe>/', views.billa_produktgruppe_detail, name='billa_produktgruppe_detail'),

    # Mapper & Speichern
    path('produktgruppen/mapper/', views.billa_produktgruppen_mapper, name='billa_produktgruppen_mapper'),

    # Marken
    path('marken/', views.billa_marken_liste, name='billa_marken_liste'),
    path('marke/<str:marke>/', views.billa_marke_detail, name='billa_marke_detail'),

    # Billa API Endpoints
    path('api/preisverlauf/<int:produkt_id>/', stats.billa_api_preisverlauf, name='billa_api_preisverlauf'),
    path('api/stats/', stats.billa_api_stats, name='api_stats'),

    path('api/bulk-update-by-name/', views.bulk_update_by_name, name='bulk_update_by_name'),
]