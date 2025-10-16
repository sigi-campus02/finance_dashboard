from django.contrib import admin
from .models import ScheduledTransaction
from .models import RegisteredDevice

@admin.register(ScheduledTransaction)
class ScheduledTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'payee', 'amount_display', 'target_table', 'frequency',
        'next_execution_date', 'days_until_next', 'is_active', 'is_overdue'
    ]
    list_filter = ['is_active', 'frequency', 'target_table']
    search_fields = ['payee__payee', 'memo', 'category__category']
    readonly_fields = ['created_at', 'updated_at', 'days_until_next', 'is_overdue']

    fieldsets = (
        ('Ziel', {
            'fields': ('target_table', 'is_active')
        }),
        ('Transaktionsdetails', {
            'fields': (
                'account', 'flag', 'payee', 'category',
                'memo', 'outflow', 'inflow'
            )
        }),
        ('Wiederholung', {
            'fields': (
                'frequency', 'start_date', 'end_date',
                'next_execution_date'
            )
        }),
        ('Status', {
            'fields': ('days_until_next', 'is_overdue'),
            'classes': ('collapse',)
        }),
        ('Metadaten', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def amount_display(self, obj):
        """Zeigt Betrag mit Typ an"""
        if obj.outflow:
            return f"-€{obj.outflow}"
        elif obj.inflow:
            return f"+€{obj.inflow}"
        return "€0"

    amount_display.short_description = 'Betrag'

    def days_until_next(self, obj):
        """Zeigt Tage bis zur nächsten Ausführung"""
        days = obj.days_until_next
        if days < 0:
            return f"Überfällig ({abs(days)} Tage)"
        elif days == 0:
            return "Heute"
        return f"{days} Tage"

    days_until_next.short_description = 'Bis nächste Ausführung'

    def is_overdue(self, obj):
        """Zeigt ob überfällig"""
        return obj.is_overdue

    is_overdue.boolean = True
    is_overdue.short_description = 'Überfällig'

    actions = ['execute_now', 'activate', 'deactivate']

    def execute_now(self, request, queryset):
        """Admin-Action: Sofort ausführen"""
        executed = 0
        for scheduled_tx in queryset:
            try:
                transaction = scheduled_tx.execute()
                if transaction:
                    executed += 1
            except Exception as e:
                self.message_user(
                    request,
                    f"Fehler bei {scheduled_tx.payee}: {str(e)}",
                    level='ERROR'
                )

        self.message_user(
            request,
            f"{executed} Transaktion(en) erfolgreich ausgeführt."
        )

    execute_now.short_description = "Ausgewählte jetzt ausführen"

    def activate(self, request, queryset):
        """Admin-Action: Aktivieren"""
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} Transaktion(en) aktiviert.")

    activate.short_description = "Aktivieren"

    def deactivate(self, request, queryset):
        """Admin-Action: Deaktivieren"""
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} Transaktion(en) deaktiviert.")

    deactivate.short_description = "Deaktivieren"


@admin.register(RegisteredDevice)
class RegisteredDeviceAdmin(admin.ModelAdmin):
    list_display = ['user', 'device_name', 'is_active', 'last_used', 'created_at']
    list_filter = ['is_active', 'user']
    search_fields = ['user__username', 'device_name']
    actions = ['deactivate_devices', 'activate_devices']

    def deactivate_devices(self, request, queryset):
        queryset.update(is_active=False)

    deactivate_devices.short_description = "Deaktiviere ausgewählte Geräte"