from django.core.validators import MinValueValidator
from decimal import Decimal
from django.db import models


# ===== BILLA MODELS =====


class BillaEinkauf(models.Model):
    """Billa Einkauf - Haupt-Rechnung"""
    datum = models.DateField(db_index=True, verbose_name="Einkaufsdatum")
    zeit = models.TimeField(null=True, blank=True, verbose_name="Uhrzeit")
    filiale = models.ForeignKey(
        'BillaFiliale',
        on_delete=models.PROTECT,
        verbose_name="Filiale",
        related_name='einkauefe'
    )
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
        app_label = 'billa'
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
        app_label = 'billa'
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

    name_korrigiert = models.CharField(
        max_length=500,
        db_index=True,
        null=True,
        blank=True,
        verbose_name="Korrigierter Name",
        help_text="Manuell korrigierter/vereinheitlichter Produktname"
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
        app_label = 'billa'
        db_table = 'billa_produkt'
        verbose_name = "Billa Produkt"
        verbose_name_plural = "Billa Produkte"
        ordering = ['name_normalisiert']
        indexes = [
            models.Index(fields=['name_normalisiert']),
            models.Index(fields=['ueberkategorie']),
            models.Index(fields=['name_korrigiert']),
        ]

    def __str__(self):
        return self.name_korrigiert or self.name_normalisiert

    @property
    def display_name(self):
        """Gibt den korrigierten Namen zurück, falls vorhanden, sonst normalisiert"""
        return self.name_korrigiert or self.name_normalisiert


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
    filiale = models.ForeignKey(
        'BillaFiliale',
        on_delete=models.PROTECT,
        verbose_name="Filiale",
        related_name='preishistorie'
    )

    class Meta:
        app_label = 'billa'
        db_table = 'billa_preis_historie'
        verbose_name = "Billa Preishistorie"
        verbose_name_plural = "Billa Preishistorie"
        ordering = ['-datum']
        indexes = [
            models.Index(fields=['produkt', 'datum']),
            models.Index(fields=['datum']),
            models.Index(fields=['filiale']),
        ]

    def __str__(self):
        return f"{self.produkt.name_normalisiert} - {self.datum} ({self.filiale}): € {self.preis}"


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
        app_label = 'billa'
        db_table = 'billa_filialen'
        verbose_name = "Billa Filiale"
        verbose_name_plural = "Billa Filialen"
        ordering = ['filial_nr']

    def __str__(self):
        typ_name = "Billa Plus" if self.typ == 'billa_plus' else "Billa"
        return f"{typ_name} - {self.name}"

    @property
    def vollstaendiger_name(self):
        """Gibt den vollen Namen mit Filialnummer zurück"""
        typ_name = "Billa Plus" if self.typ == 'billa_plus' else "Billa"
        return f"{self.filial_nr} - {typ_name} - {self.name}"
