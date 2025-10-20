# bitpanda/models.py
from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal


class BitpandaHolding(models.Model):
    """
    Asset-Definition (nicht mehr Bestand, nur noch Metadaten)
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='bitpanda_holdings'
    )

    asset = models.CharField(
        max_length=50,
        help_text="Asset Symbol (z.B. BTC, ETH, AAPL)"
    )

    asset_class = models.CharField(
        max_length=50,
        help_text="Asset-Klasse"
    )

    # Metadaten
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Bitpanda Asset"
        verbose_name_plural = "Bitpanda Assets"
        unique_together = ['user', 'asset']
        ordering = ['asset']

    def __str__(self):
        return f"{self.user.username} - {self.asset}"

    @property
    def current_balance(self):
        """Berechnet aktuellen Bestand aus BitpandaAssetValue"""
        transactions = self.historical_values.all()
        return sum(tx.units for tx in transactions if tx.units) or Decimal('0')

    @property
    def total_invested(self):
        """Berechnet investierten Betrag aus BitpandaAssetValue"""
        transactions = self.historical_values.filter(units__gt=0)  # Nur Käufe
        return sum(tx.payed for tx in transactions if tx.payed) or Decimal('0')

    @property
    def current_price(self):
        """Letzter bekannter Preis"""
        last_tx = self.historical_values.order_by('-date').first()
        return last_tx.price_per_unit if last_tx else Decimal('0')

    @property
    def current_value(self):
        """Aktueller Wert = Bestand × Preis"""
        return self.current_balance * self.current_price


class BitpandaAssetValue(models.Model):
    """
    Historische Transaktionen und Preise
    """
    holding = models.ForeignKey(
        BitpandaHolding,
        on_delete=models.CASCADE,
        related_name='historical_values',
        help_text="Referenz zum Asset"
    )

    date = models.DateField(
        help_text="Datum der Transaktion oder Preisupdate"
    )

    payed = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Bezahlter/Erhaltener Betrag in EUR (positiv bei Kauf, negativ bei Verkauf)"
    )

    units = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Anzahl gekaufter/verkaufter Einheiten (positiv bei Kauf, negativ bei Verkauf)"
    )

    price_per_unit = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        help_text="Preis pro Einheit"
    )

    # Metadaten
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Asset-Transaktion"
        verbose_name_plural = "Asset-Transaktionen"
        ordering = ['-date']
        indexes = [
            models.Index(fields=['holding', 'date']),
            models.Index(fields=['date']),
        ]

    def __str__(self):
        if self.units is not None and self.units != 0:
            action = 'Kauf' if self.units > 0 else 'Verkauf'
            return f"{self.holding.asset} - {self.date} - {action}: {abs(self.units)} Einheiten"
        return f"{self.holding.asset} - {self.date} - Preis: €{self.price_per_unit}"

    @property
    def transaction_type(self):
        """Gibt 'Kauf', 'Verkauf' oder 'Preisupdate' zurück"""
        if self.units is None or self.units == 0:
            return 'Preisupdate'
        return 'Kauf' if self.units > 0 else 'Verkauf'

    @property
    def total_value(self):
        """Berechnet den Gesamtwert: units × price_per_unit"""
        if self.units is None:
            return None
        return abs(self.units * self.price_per_unit)