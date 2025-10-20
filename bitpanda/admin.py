from django.contrib import admin
from .models import BitpandaSnapshot


@admin.register(BitpandaSnapshot)
class BitpandaSnapshotAdmin(admin.ModelAdmin):
    """
    Admin Interface für Bitpanda Portfolio Snapshots
    """
    list_display = [
        'user',
        'snapshot_date',
        'total_value_eur',
        'total_crypto_value_eur',
        'total_fiat_value_eur',
        'total_commodities_value_eur'
    ]
    list_filter = ['snapshot_date', 'user']
    search_fields = ['user__username']
    readonly_fields = [
        'snapshot_date',
        'raw_data',
        'formatted_raw_data'
    ]
    date_hierarchy = 'snapshot_date'

    fieldsets = (
        ('Benutzer', {
            'fields': ('user',)
        }),
        ('Portfolio Werte (EUR)', {
            'fields': (
                'total_value_eur',
                'total_crypto_value_eur',
                'total_fiat_value_eur',
                'total_commodities_value_eur'
            )
        }),
        ('Metadaten', {
            'fields': ('snapshot_date',)
        }),
        ('Raw Daten (Read-Only)', {
            'fields': ('formatted_raw_data',),
            'classes': ('collapse',),
            'description': 'Original API Response für Debugging'
        }),
    )

    def formatted_raw_data(self, obj):
        """
        Zeigt die Raw-Daten formatiert an
        """
        if obj.raw_data:
            import json
            from django.utils.html import format_html
            formatted = json.dumps(obj.raw_data, indent=2, ensure_ascii=False)
            return format_html('<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px;">{}</pre>',
                               formatted)
        return "-"

    formatted_raw_data.short_description = "API Response (formatiert)"

    def has_add_permission(self, request):
        """
        Snapshots werden nur über die Synchronisations-Funktion erstellt,
        nicht manuell im Admin
        """
        return False

    def has_change_permission(self, request, obj=None):
        """
        Snapshots sind Read-Only nach der Erstellung
        """
        return False

    # Erlaube das Löschen von alten Snapshots
    def has_delete_permission(self, request, obj=None):
        return True

    actions = ['delete_selected']

    class Meta:
        verbose_name = "Bitpanda Snapshot"
        verbose_name_plural = "Bitpanda Snapshots"