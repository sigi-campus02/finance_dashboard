from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


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


# ===== BILLA MODELS =====

class BillaEinkauf(models.Model):
    """Billa Einkauf - Haupt-Rechnung"""
    datum = models.DateField(db_index=True, verbose_name="Einkaufsdatum")
    zeit = models.TimeField(null=True, blank=True, verbose_name="Uhrzeit")
    filiale = models.CharField(max_length=20, db_index=True, verbose_name="Filiale")
    kassa = models.IntegerField(null=True, blank=True, verbose_name="Kassa-Nr")
    bon_nr = models.CharField(max_length=50, null=True, blank=True, verbose_name="Bon-Nummer")
    re_nr = models.CharField(max_length=100, unique=True, verbose_name="Rechnungsnummer")

    # Preise
    gesamt_preis = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Gesamtpreis"
    )
    gesamt_ersparnis = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Gesamte Ersparnis"
    )
    zwischensumme = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Zwischensumme"
    )

    # MwSt
    mwst_b = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="MwSt 10%")
    mwst_c = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="MwSt 20%")
    mwst_g = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="MwSt 13%")
    mwst_d = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="MwSt 0%")

    # Ö-Punkte
    oe_punkte_gesammelt = models.IntegerField(default=0, verbose_name="Ö-Punkte gesammelt")
    oe_punkte_eingeloest = models.IntegerField(default=0, verbose_name="Ö-Punkte eingelöst")

    # Meta
    pdf_datei = models.CharField(max_length=500, null=True, blank=True, verbose_name="PDF-Datei")
    import_datum = models.DateTimeField(auto_now_add=True, verbose_name="Import-Datum")
    notizen = models.TextField(null=True, blank=True, verbose_name="Notizen")

    class Meta:
        db_table = 'billa_einkauf'
        verbose_name = "Billa Einkauf"
        verbose_name_plural = "Billa Einkäufe"
        ordering = ['-datum', '-zeit']
        indexes = [
            models.Index(fields=['datum', 'filiale']),
            models.Index(fields=['re_nr']),
        ]

    def __str__(self):
        return f"{self.datum} - {self.filiale} (€ {self.gesamt_preis})"

    @property
    def anzahl_artikel(self):
        """Gibt die Anzahl der Artikel zurück"""
        return self.artikel.count()

    @property
    def ersparnis_prozent(self):
        """Berechnet die Ersparnis in Prozent"""
        if self.gesamt_preis > 0:
            original_preis = self.gesamt_preis + self.gesamt_ersparnis
            return (self.gesamt_ersparnis / original_preis) * 100
        return 0


class BillaArtikel(models.Model):
    """Billa Artikel - Einzelner Artikel auf der Rechnung"""

    MWST_CHOICES = [
        ('A', '0% (Pfand)'),
        ('B', '10% (Lebensmittel)'),
        ('C', '20% (Standard)'),
        ('D', 'Steuerfrei'),
        ('G', '13% (Sonstige)'),
    ]

    einkauf = models.ForeignKey(
        BillaEinkauf,
        on_delete=models.CASCADE,
        related_name='artikel',
        verbose_name="Einkauf"
    )

    position = models.IntegerField(verbose_name="Position auf Rechnung")

    # Produktinfo
    produkt_name = models.CharField(max_length=500, verbose_name="Produktname")
    produkt_name_normalisiert = models.CharField(
        max_length=500,
        db_index=True,
        verbose_name="Produktname (normalisiert)"
    )
    produkt = models.ForeignKey(
        'BillaProdukt',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='artikel',
        verbose_name="Produkt"
    )

    # Menge & Preis
    menge = models.DecimalField(max_digits=10, decimal_places=3, default=1, verbose_name="Menge")
    einheit = models.CharField(max_length=20, default='Stk', verbose_name="Einheit")
    einzelpreis = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Einzelpreis"
    )
    gesamtpreis = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Gesamtpreis")
    preis_pro_einheit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Preis pro Einheit",
        help_text="Automatisch berechnet: gesamtpreis / menge"
    )

    # Rabatte
    rabatt = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Rabatt")
    rabatt_typ = models.CharField(max_length=100, null=True, blank=True, verbose_name="Rabatt-Typ")

    # Eigenschaften
    mwst_kategorie = models.CharField(max_length=1, choices=MWST_CHOICES, verbose_name="MwSt-Kategorie")
    ist_gewichtsartikel = models.BooleanField(default=False, verbose_name="Gewichtsartikel")
    ist_mehrfachgebinde = models.BooleanField(default=False, verbose_name="Mehrfachgebinde")

    class Meta:
        db_table = 'billa_artikel'
        verbose_name = "Billa Artikel"
        verbose_name_plural = "Billa Artikel"
        ordering = ['einkauf', 'position']
        indexes = [
            models.Index(fields=['produkt_name_normalisiert']),
            models.Index(fields=['einkauf', 'position']),
        ]

    def __str__(self):
        return f"{self.produkt_name} (€ {self.gesamtpreis})"

    def save(self, *args, **kwargs):
        """Berechne preis_pro_einheit beim Speichern"""
        if self.menge > 0:
            self.preis_pro_einheit = self.gesamtpreis / self.menge
        else:
            self.preis_pro_einheit = self.gesamtpreis
        super().save(*args, **kwargs)


class BillaProdukt(models.Model):
    """Billa Produkt - Normalisierte Produktdaten"""

    name_original = models.CharField(
        max_length=500,
        verbose_name="Original-Name",
        help_text="Eine der Original-Varianten dieses Produkts"
    )

    name_normalisiert = models.CharField(
        max_length=500,
        db_index=True,
        unique=True,
        verbose_name="Normalisierter Name"
    )

    # Überkategorie (ersetzt die alte kategorie)
    ueberkategorie = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        verbose_name='Überkategorie',
        help_text='Übergeordnete Kategorie wie Gemüse, Obst, Milchprodukte, etc.'
    )

    # Spezifische Produktgruppe
    produktgruppe = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name='Produktgruppe'
    )

    marke = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        verbose_name="Marke"
    )

    # Statistiken
    durchschnittspreis = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Durchschnittspreis"
    )
    letzter_preis = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Letzter Preis"
    )
    anzahl_kaeufe = models.IntegerField(default=0, verbose_name="Anzahl Käufe")
    letzte_aktualisierung = models.DateTimeField(auto_now=True, verbose_name="Letzte Aktualisierung")

    class Meta:
        db_table = 'billa_produkt'
        verbose_name = "Billa Produkt"
        verbose_name_plural = "Billa Produkte"
        ordering = ['name_normalisiert']
        indexes = [
            models.Index(fields=['name_normalisiert']),
            models.Index(fields=['ueberkategorie']),
        ]

    def __str__(self):
        return self.name_normalisiert

    def update_statistiken(self):
        """Aktualisiert die Statistiken für dieses Produkt"""
        from django.db.models import Avg, Max, Count

        stats = self.artikel.aggregate(
            avg_preis=Avg('preis_pro_einheit'),
            letzter_preis=Max('einkauf__datum'),
            anzahl=Count('id')
        )

        if stats['avg_preis']:
            self.durchschnittspreis = stats['avg_preis']

        if stats['letzter_preis']:
            letzter_artikel = self.artikel.filter(
                einkauf__datum=stats['letzter_preis']
            ).first()
            if letzter_artikel:
                self.letzter_preis = letzter_artikel.preis_pro_einheit

        self.anzahl_kaeufe = stats['anzahl'] or 0
        self.save(update_fields=['durchschnittspreis', 'letzter_preis', 'anzahl_kaeufe'])


class BillaPreisHistorie(models.Model):
    """Billa Preishistorie - Tracking von Preisänderungen"""

    produkt = models.ForeignKey(
        BillaProdukt,
        on_delete=models.CASCADE,
        related_name='preishistorie',
        verbose_name="Produkt"
    )
    artikel = models.ForeignKey(
        BillaArtikel,
        on_delete=models.CASCADE,
        related_name='preishistorie',
        verbose_name="Artikel"
    )

    datum = models.DateField(db_index=True, verbose_name="Datum")
    preis = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Preis")
    menge = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Menge")
    einheit = models.CharField(max_length=20, verbose_name="Einheit")
    filiale = models.CharField(max_length=20, verbose_name="Filiale")

    class Meta:
        db_table = 'billa_preis_historie'
        verbose_name = "Billa Preishistorie"
        verbose_name_plural = "Billa Preishistorie"
        ordering = ['-datum']
        indexes = [
            models.Index(fields=['produkt', 'datum']),
            models.Index(fields=['datum']),
        ]

    def __str__(self):
        return f"{self.produkt.name_normalisiert} - {self.datum}: € {self.preis}"


class BillaFiliale(models.Model):
    """Billa Filiale - Informationen zu den einzelnen Filialen"""

    filial_nr = models.CharField(
        max_length=10,
        primary_key=True,
        verbose_name="Filial-Nummer"
    )

    name = models.CharField(
        max_length=200,
        verbose_name="Filialname"
    )

    typ = models.CharField(
        max_length=20,
        choices=[
            ('billa', 'Billa'),
            ('billa_plus', 'Billa Plus'),
        ],
        verbose_name="Filialtyp"
    )

    # Optional: Weitere Felder für zukünftige Erweiterungen
    adresse = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Adresse"
    )

    plz = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        verbose_name="Postleitzahl"
    )

    ort = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Ort"
    )

    aktiv = models.BooleanField(
        default=True,
        verbose_name="Aktiv"
    )

    class Meta:
        db_table = 'billa_filialen'
        verbose_name = "Billa Filiale"
        verbose_name_plural = "Billa Filialen"
        ordering = ['filial_nr']

    def __str__(self):
        return f"{self.filial_nr} - {self.name}"