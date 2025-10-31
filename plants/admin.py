# plants/admin.py
from django.contrib import admin
from django.utils.html import format_html
from .models import Plant, PlantGroup, PlantImage, PlantRoom


# ---------- PlantRoom ----------
@admin.register(PlantRoom)
class PlantRoomAdmin(admin.ModelAdmin):
    list_display = ("name", "is_outdoor", "user")
    list_filter = ("is_outdoor",)
    search_fields = ("name",)
    autocomplete_fields = ("user",)
    ordering = ("name",)


# ---------- PlantGroup ----------
@admin.register(PlantGroup)
class PlantGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "plant_count_disp", "created_at")
    list_filter = ("user", "created_at")
    search_fields = ("name", "description")
    readonly_fields = ("created_at",)
    ordering = ("name",)

    @admin.display(description="Anzahl Pflanzen")
    def plant_count_disp(self, obj):
        return obj.plant_count()


# ---------- Inline für Bilder ----------
class PlantImageInline(admin.TabularInline):
    model = PlantImage
    extra = 0
    fields = ("preview", "image", "captured_at", "notes")
    readonly_fields = ("captured_at", "preview")

    @admin.display(description="Vorschau")
    def preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:60px;width:auto;border-radius:4px;object-fit:cover;" />',
                obj.image.url
            )
        return "—"


# ---------- Plant ----------
@admin.register(Plant)
class PlantAdmin(admin.ModelAdmin):
    list_display = ("name", "group", "species", "user", "room_list", "image_count_disp", "created_at")
    list_filter = ("group", "rooms", "user", "created_at")
    search_fields = ("name", "species")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("group", "user", "rooms")
    inlines = [PlantImageInline]
    save_on_top = True
    ordering = ("group__name", "name")

    @admin.display(description="Anzahl Bilder")
    def image_count_disp(self, obj):
        return obj.image_count()

    @admin.display(description="Räume")
    def room_list(self, obj):
        names = obj.rooms.values_list("name", flat=True)
        return ", ".join(names) if names else "—"


# ---------- PlantImage ----------
@admin.register(PlantImage)
class PlantImageAdmin(admin.ModelAdmin):
    list_display = ("preview_small", "plant", "captured_at", "image")
    list_filter = ("plant__group", "plant__rooms", "captured_at")
    search_fields = ("plant__name", "notes")
    readonly_fields = ("captured_at", "preview_large")
    date_hierarchy = "captured_at"
    ordering = ("-captured_at",)
    fields = ("plant", "image", "captured_at", "notes", "preview_large")

    @admin.display(description="")
    def preview_small(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:40px;width:auto;border-radius:3px;object-fit:cover;" />',
                obj.image.url
            )
        return "—"

    @admin.display(description="Vorschau")
    def preview_large(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height:240px;width:auto;border-radius:6px;object-fit:contain;" />',
                obj.image.url
            )
        return "—"
