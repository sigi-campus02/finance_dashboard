from django.contrib import admin
from .models import (
    BillaFiliale)


@admin.register(BillaFiliale)
class BillaFilialeAdmin(admin.ModelAdmin):
    list_display = ['filial_nr', 'name', 'typ', 'aktiv']
    list_filter = ['typ', 'aktiv']
    search_fields = ['filial_nr', 'name', 'ort']
