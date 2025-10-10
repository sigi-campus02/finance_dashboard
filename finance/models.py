from django.db import models


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