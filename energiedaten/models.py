# models.py
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import ExtractYear, ExtractMonth, ExtractQuarter, ExtractWeek, ExtractIsoWeekDay


class Stromverbrauch(models.Model):
    """Faktentabelle für täglichen Stromverbrauch"""

    datum = models.DateField(unique=True, db_index=True, verbose_name="Datum")
    verbrauch_kwh = models.DecimalField(
        max_digits=10,
        decimal_places=5,
        verbose_name="Verbrauch (kWh)"
    )

    # Zeitdimensionen - werden per Property berechnet
    erstellt_am = models.DateTimeField(auto_now_add=True)
    aktualisiert_am = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'fact_stromverbrauch'
        verbose_name = 'Stromverbrauch'
        verbose_name_plural = 'Stromverbräuche'
        ordering = ['-datum']
        indexes = [
            models.Index(fields=['-datum'], name='idx_strom_datum'),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(verbrauch_kwh__gte=0),
                name='chk_verbrauch_positiv'
            )
        ]

    @property
    def jahr(self):
        return self.datum.year

    @property
    def monat(self):
        return self.datum.month

    @property
    def quartal(self):
        return (self.datum.month - 1) // 3 + 1

    @property
    def wochentag(self):
        """ISO Wochentag (1=Montag, 7=Sonntag)"""
        return self.datum.isoweekday()

    @property
    def kalenderwoche(self):
        return self.datum.isocalendar()[1]

    def __str__(self):
        return f"{self.datum}: {self.verbrauch_kwh} kWh"