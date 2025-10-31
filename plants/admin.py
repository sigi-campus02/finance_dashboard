# plants/admin.py
from django.contrib import admin
from .models import PlantGroup, Plant, PlantImage


@admin.register(PlantGroup)
class PlantGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'plant_count', 'created_at']
    list_filter = ['user', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at']

    def plant_count(self, obj):
        return obj.plant_count()

    plant_count.short_description = 'Anzahl Pflanzen'


class PlantImageInline(admin.TabularInline):
    model = PlantImage
    extra = 0
    readonly_fields = ['captured_at', 'image']
    fields = ['image', 'captured_at', 'notes']


@admin.register(Plant)
class PlantAdmin(admin.ModelAdmin):
    list_display = ['name', 'group', 'species', 'user', 'image_count', 'created_at']
    list_filter = ['group', 'user', 'created_at']
    search_fields = ['name', 'species']
    readonly_fields = ['created_at']
    inlines = [PlantImageInline]

    def image_count(self, obj):
        return obj.image_count()

    image_count.short_description = 'Anzahl Bilder'


@admin.register(PlantImage)
class PlantImageAdmin(admin.ModelAdmin):
    list_display = ['plant', 'captured_at', 'image']
    list_filter = ['plant__group', 'plant', 'captured_at']
    search_fields = ['plant__name', 'notes']
    readonly_fields = ['captured_at']
    date_hierarchy = 'captured_at'