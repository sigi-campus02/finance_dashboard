from django.db import models
from django.contrib.auth.models import User
import uuid


# ===== DIMENSION MODELS =====

class DimAccountTypes(models.Model):
    """Kontotypen"""
    id = models.AutoField(primary_key=True)  # Explizit definiert
    accounttypes = models.CharField(max_length=500)

    class Meta:
        db_table = 'dim_accounttypes'
        managed = False

    def __str__(self):
        return self.accounttypes


class DimAccount(models.Model):
    """Konten"""
    id = models.AutoField(primary_key=True)  # Explizit definiert
    account = models.CharField(max_length=500)
    accounttype = models.ForeignKey(
        DimAccountTypes,
        on_delete=models.DO_NOTHING,
        db_column='accounttype_id',
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'dim_account'
        managed = False

    def __str__(self):
        return self.account


class DimFlag(models.Model):
    """Flags/Markierungen"""
    id = models.AutoField(primary_key=True)  # Explizit definiert
    flag = models.CharField(max_length=500)

    class Meta:
        db_table = 'dim_flag'
        managed = False

    def __str__(self):
        return self.flag or 'Keine Flag'


class DimPayee(models.Model):
    """Zahlungsempfänger"""
    id = models.AutoField(primary_key=True)  # ← WICHTIG: Explizit definiert für Auto-Increment
    payee = models.CharField(max_length=500)
    payee_type = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = 'dim_payee'
        managed = False

    def __str__(self):
        return self.payee

    @property
    def is_transfer(self):
        """Prüft ob es sich um einen Transfer handelt"""
        return self.payee_type == 'transfer'

    @property
    def is_kursschwankung(self):
        """Prüft ob es sich um eine Kursschwankung handelt"""
        return self.payee_type == 'kursschwankung'

    @property
    def exclude_from_stats(self):
        """Prüft ob diese Transaktion aus Statistiken ausgeschlossen werden soll"""
        return self.payee_type in ['transfer', 'kursschwankung']


class DimCategoryGroup(models.Model):
    """Kategoriegruppen"""
    id = models.AutoField(primary_key=True)  # Explizit definiert
    category_group = models.CharField(max_length=500, db_column='category_group')

    class Meta:
        db_table = 'dim_categorygroup'
        managed = False

    def __str__(self):
        return self.category_group


class DimCategory(models.Model):
    """Kategorien"""
    id = models.AutoField(primary_key=True)  # Explizit definiert
    category = models.CharField(max_length=500)
    categorygroup = models.ForeignKey(
        DimCategoryGroup,
        on_delete=models.DO_NOTHING,
        db_column='categorygroup_id',
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'dim_category'
        managed = False

    def __str__(self):
        return self.category


class DimMonat(models.Model):
    """Monate"""
    id = models.AutoField(primary_key=True)  # Explizit definiert
    monat = models.CharField(max_length=500)

    class Meta:
        db_table = 'dim_monat'
        managed = False

    def __str__(self):
        return self.monat


class DimJahr(models.Model):
    """Jahre"""
    jahr = models.IntegerField(primary_key=True)

    class Meta:
        db_table = 'dim_jahr'
        managed = False

    def __str__(self):
        return str(self.jahr)


class DimCalender(models.Model):
    """Kalender/Datum-Dimension"""
    datum = models.DateField(primary_key=True)
    jahr = models.IntegerField()
    monat = models.ForeignKey(
        DimMonat,
        on_delete=models.DO_NOTHING,
        db_column='monat_id',
        null=True,
        blank=True
    )
    wochentag = models.CharField(max_length=500)
    kalenderwoche = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'dim_calender'
        managed = False

    def __str__(self):
        return str(self.datum)


# ===== FAKTEN MODELS =====

class FactTransactionsSigi(models.Model):
    """Transaktionen Sigi"""
    id = models.AutoField(primary_key=True)  # Explizit definiert
    account = models.ForeignKey(
        DimAccount,
        on_delete=models.DO_NOTHING,
        db_column='account_id',
        null=True,
        blank=True
    )
    flag = models.ForeignKey(
        DimFlag,
        on_delete=models.DO_NOTHING,
        db_column='flag_id',
        null=True,
        blank=True
    )
    date = models.DateField()
    payee = models.ForeignKey(
        DimPayee,
        on_delete=models.DO_NOTHING,
        db_column='payee_id',
        null=True,
        blank=True
    )
    category = models.ForeignKey(
        DimCategory,
        on_delete=models.DO_NOTHING,
        db_column='category_id',
        null=True,
        blank=True
    )
    memo = models.TextField(null=True, blank=True)
    outflow = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    inflow = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'fact_transactions_sigi'
        managed = False
        ordering = ['-date']

    def __str__(self):
        return f"{self.date} - {self.payee} - {self.outflow or self.inflow}"

    @property
    def netto(self):
        """Berechnet Netto (Inflow - Outflow)"""
        inflow = self.inflow or 0
        outflow = self.outflow or 0
        return inflow - outflow

    @property
    def is_transfer(self):
        """Prüft ob es sich um einen Transfer handelt"""
        return self.payee and self.payee.is_transfer

    @property
    def is_kursschwankung(self):
        """Prüft ob es sich um eine Kursschwankung handelt"""
        return self.payee and self.payee.is_kursschwankung

    @property
    def exclude_from_stats(self):
        """Prüft ob aus Statistiken ausgeschlossen"""
        return self.payee and self.payee.exclude_from_stats


class FactTransactionsRobert(models.Model):
    """Transaktionen Robert"""
    id = models.AutoField(primary_key=True)  # Explizit definiert
    account = models.ForeignKey(
        DimAccount,
        on_delete=models.DO_NOTHING,
        db_column='account_id',
        null=True,
        blank=True
    )
    flag = models.ForeignKey(
        DimFlag,
        on_delete=models.DO_NOTHING,
        db_column='flag_id',
        null=True,
        blank=True
    )
    date = models.DateField()
    payee = models.ForeignKey(
        DimPayee,
        on_delete=models.DO_NOTHING,
        db_column='payee_id',
        null=True,
        blank=True
    )
    category = models.ForeignKey(
        DimCategory,
        on_delete=models.DO_NOTHING,
        db_column='category_id',
        null=True,
        blank=True
    )
    memo = models.TextField(null=True, blank=True)
    outflow = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    inflow = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'fact_transactions_robert'
        managed = False
        ordering = ['-date']

    def __str__(self):
        return f"{self.date} - {self.payee} - {self.outflow or self.inflow}"

    @property
    def is_transfer(self):
        """Prüft ob es sich um einen Transfer handelt"""
        return self.payee and self.payee.is_transfer

    @property
    def is_kursschwankung(self):
        """Prüft ob es sich um eine Kursschwankung handelt"""
        return self.payee and self.payee.is_kursschwankung

    @property
    def exclude_from_stats(self):
        """Prüft ob aus Statistiken ausgeschlossen"""
        return self.payee and self.payee.exclude_from_stats


class FactBetriebskosten(models.Model):
    """Betriebskosten"""
    id = models.AutoField(primary_key=True)  # Explizit definiert
    jahr = models.IntegerField()
    monat = models.IntegerField()
    vs_posten = models.CharField(max_length=500)
    wohnung_betrag_netto = models.DecimalField(max_digits=18, decimal_places=2, null=True)
    wohnung_betrag_brutto = models.DecimalField(max_digits=18, decimal_places=2, null=True)
    tg_betrag_netto = models.DecimalField(max_digits=18, decimal_places=2, null=True)
    tg_betrag_brutto = models.DecimalField(max_digits=18, decimal_places=2, null=True)
    gesamt_betrag_brutto = models.DecimalField(max_digits=18, decimal_places=2, null=True)

    class Meta:
        db_table = 'fact_betriebskosten'
        managed = False


class FactAssetsLiabilitiesOverview(models.Model):
    """
    Vermögensübersicht - mappt auf bestehende Tabelle
    """
    id = models.AutoField(primary_key=True)  # Explizit definiert
    asset_name = models.CharField(max_length=500, null=True, blank=True)
    balance = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    date_zone = models.DateField(null=True, blank=True)
    category = models.CharField(max_length=500, null=True, blank=True)

    class Meta:
        db_table = 'fact_assets_liabilities_overview'
        managed = False
        ordering = ['category', 'asset_name', '-date_zone']

    def __str__(self):
        return f"{self.asset_name} - {self.date_zone}: €{self.balance}"


class DimAssetCategory(models.Model):
    """
    Asset-Kategorien (falls als separate Tabelle vorhanden)
    """
    id = models.AutoField(primary_key=True)  # Explizit definiert
    category = models.CharField(max_length=500)
    display_name = models.CharField(max_length=500, null=True, blank=True)
    category_order = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'dim_asset_category'
        managed = False

    def __str__(self):
        return self.display_name or self.category


class ScheduledTransaction(models.Model):
    """
    Wiederkehrende Transaktionen die automatisch erstellt werden
    """
    FREQUENCY_CHOICES = [
        ('monthly', 'Monatlich'),
        ('quarterly', 'Vierteljährlich'),
        ('yearly', 'Jährlich'),
    ]

    TABLE_CHOICES = [
        ('sigi', 'Sigi'),
        ('robert', 'Robert'),
    ]

    # Welche Tabelle soll verwendet werden
    target_table = models.CharField(
        max_length=10,
        choices=TABLE_CHOICES,
        default='sigi'
    )

    # Transaktionsdetails
    account = models.ForeignKey(
        DimAccount,
        on_delete=models.CASCADE,
        db_column='account_id'
    )
    flag = models.ForeignKey(
        DimFlag,
        on_delete=models.SET_NULL,
        db_column='flag_id',
        null=True,
        blank=True
    )
    payee = models.ForeignKey(
        DimPayee,
        on_delete=models.CASCADE,
        db_column='payee_id'
    )
    category = models.ForeignKey(
        DimCategory,
        on_delete=models.CASCADE,
        db_column='category_id'
    )
    memo = models.TextField(null=True, blank=True)
    outflow = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True
    )
    inflow = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Scheduling Details
    frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default='monthly'
    )
    start_date = models.DateField(
        help_text="Datum der ersten Transaktion"
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Optional: Enddatum für wiederkehrende Transaktionen"
    )
    next_execution_date = models.DateField(
        help_text="Nächstes Datum für die automatische Erstellung"
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Aktive Transaktionen werden automatisch erstellt"
    )

    # Metadaten
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = 'scheduled_transactions'
        ordering = ['next_execution_date', 'payee']
        verbose_name = 'Scheduled Transaction'
        verbose_name_plural = 'Scheduled Transactions'

    def __str__(self):
        amount = self.outflow or self.inflow or 0
        return f"{self.payee} - €{amount} ({self.get_frequency_display()})"

    def calculate_next_execution_date(self, current_date=None):
        """
        Berechnet das nächste Ausführungsdatum basierend auf Frequenz
        """
        from dateutil.relativedelta import relativedelta

        if current_date is None:
            current_date = self.next_execution_date

        if self.frequency == 'monthly':
            return current_date + relativedelta(months=1)
        elif self.frequency == 'quarterly':
            return current_date + relativedelta(months=3)
        elif self.frequency == 'yearly':
            return current_date + relativedelta(years=1)

        return current_date

    def create_transaction(self):
        """
        Erstellt die tatsächliche Transaktion in der entsprechenden Tabelle
        """
        transaction_data = {
            'account_id': self.account_id,
            'flag_id': self.flag_id,
            'date': self.next_execution_date,
            'payee_id': self.payee_id,
            'category_id': self.category_id,
            'memo': self.memo,
            'outflow': self.outflow,
            'inflow': self.inflow,
        }

        if self.target_table == 'robert':
            transaction = FactTransactionsRobert.objects.create(**transaction_data)
        else:
            transaction = FactTransactionsSigi.objects.create(**transaction_data)

        return transaction

    def execute(self):
        """
        Führt die Scheduled Transaction aus:
        1. Erstellt Transaktion
        2. Updated next_execution_date
        """
        from datetime import date

        # Prüfe ob bereits ausgeführt
        if self.next_execution_date > date.today():
            return None

        # Prüfe ob Enddatum überschritten
        if self.end_date and self.next_execution_date > self.end_date:
            self.is_active = False
            self.save()
            return None

        # Erstelle Transaktion
        transaction = self.create_transaction()

        # Update next_execution_date
        self.next_execution_date = self.calculate_next_execution_date()
        self.save()

        return transaction

    @property
    def days_until_next(self):
        """Tage bis zur nächsten Ausführung"""
        from datetime import date
        delta = self.next_execution_date - date.today()
        return delta.days

    @property
    def is_overdue(self):
        """Prüft ob überfällig"""
        from datetime import date
        return self.is_active and self.next_execution_date < date.today()


class RegisteredDevice(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='devices')
    device_name = models.CharField(max_length=100, default='Neues Gerät')
    device_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    device_fingerprint = models.CharField(max_length=255)  # ✅ KEIN unique=True!
    is_active = models.BooleanField(default=True)
    last_used = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'finance"."registered_devices'
        unique_together = ['user', 'device_fingerprint']  # ✅ Kombination ist unique

    def __str__(self):
        return f"{self.user.username} - {self.device_name}"


class FactUrlaube(models.Model):
    """Urlaube mit Kostenaufteilung"""
    id = models.AutoField(primary_key=True)
    datum = models.DateField()
    beschreibung = models.CharField(max_length=500)
    gesamt_ausgaben = models.DecimalField(max_digits=18, decimal_places=2)
    anteil_robert = models.DecimalField(max_digits=18, decimal_places=2)
    anteil_sigi = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        db_table = 'fact_urlaube'
        managed = False
        ordering = ['-datum']
        verbose_name = 'Urlaub'
        verbose_name_plural = 'Urlaube'

    def __str__(self):
        return f"{self.datum.strftime('%d.%m.%Y')} - {self.beschreibung}"

    @property
    def calender(self):
        """Holt das zugehörige DimCalender Objekt über das datum"""
        try:
            return DimCalender.objects.get(datum=self.datum)
        except DimCalender.DoesNotExist:
            return None

    @property
    def jahr(self):
        """Gibt das Jahr zurück"""
        return self.datum.year

    @property
    def monat(self):
        """Gibt den Monat zurück"""
        return self.datum.month