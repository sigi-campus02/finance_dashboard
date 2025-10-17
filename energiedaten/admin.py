from django.contrib import admin
from .models import Stromverbrauch


@admin.register(Stromverbrauch)
class StromverbrauchAdmin(admin.ModelAdmin):
    list_display = ['datum', 'verbrauch_kwh', 'jahr', 'monat']
    list_filter = ['datum']
    date_hierarchy = 'datum'
    search_fields = ['datum']