from django.core.validators import MinValueValidator
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.db.models import Avg, Count


class BillaUeberkategorie(models.Model):
    """
    Überkategorien (z.B. Gemüse, Obst, Milchprodukte, etc.)
    """
    name = models.CharField(max_length=200, unique=True)
    icon = models.CharField(max_length=50, blank=True, null=True)  # Optional: Bootstrap Icons
    erstellt_am = models.DateTimeField(auto_now_add=True)
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Überkategorie'
        verbose_name_plural = 'Überkategorien'

    def __str__(self):
        return self.name


class BillaProduktgruppe(models.Model):
    """
    Produktgruppen innerhalb einer Überkategorie (z.B. Paprika, Tomaten unter Gemüse)
    """
    name = models.CharField(max_length=200)
    ueberkategorie = models.ForeignKey(
        BillaUeberkategorie,
        on_delete=models.CASCADE,
        related_name='produktgruppen'
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['ueberkategorie__name', 'name']
        unique_together = ['name', 'ueberkategorie']
        verbose_name = 'Produktgruppe'
        verbose_name_plural = 'Produktgruppen'

    def __str__(self):
        return f"{self.ueberkategorie.name} → {self.name}"


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
    """Produkte aus Billa-Einkäufen"""

    name_original = models.CharField(max_length=500)
    name_normalisiert = models.CharField(max_length=500)
    name_korrigiert = models.CharField(max_length=500, blank=True, null=True)
    marke = models.CharField(max_length=200, blank=True, null=True)

    # ✅ NEUE Foreign Keys
    ueberkategorie = models.ForeignKey(
        'BillaUeberkategorie',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='produkte'
    )
    produktgruppe = models.ForeignKey(
        'BillaProduktgruppe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='produkte'
    )

    anzahl_kaeufe = models.IntegerField(default=0)
    durchschnittspreis = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    letzter_preis = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ['-anzahl_kaeufe']

    def __str__(self):
        return self.name_korrigiert or self.name_normalisiert

    def update_statistiken(self):
        """Aktualisiert aggregierte Kennzahlen basierend auf vorhandenen Artikeln."""

        artikel_qs = self.artikel.select_related('einkauf')
        stats = artikel_qs.aggregate(
            total=Count('id'),
            avg_price=Avg('preis_pro_einheit'),
        )

        self.anzahl_kaeufe = stats['total'] or 0

        avg_price = stats['avg_price']
        if avg_price is None:
            avg_price = Decimal('0')
        else:
            avg_price = Decimal(avg_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.durchschnittspreis = avg_price

        letzter_preis = None
        neuester_preis = self.preishistorie.order_by('-datum', '-id').first()
        if neuester_preis:
            letzter_preis = neuester_preis.preis
        else:
            letzter_artikel = artikel_qs.order_by('-einkauf__datum', '-einkauf__zeit', '-id').first()
            if letzter_artikel:
                letzter_preis = letzter_artikel.preis_pro_einheit

        if letzter_preis is None:
            letzter_preis = Decimal('0')
        else:
            letzter_preis = Decimal(letzter_preis)

        self.letzter_preis = letzter_preis.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.save(update_fields=['anzahl_kaeufe', 'durchschnittspreis', 'letzter_preis'])


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
