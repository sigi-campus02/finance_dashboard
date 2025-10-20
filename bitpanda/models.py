from django.db import models
from django.contrib.auth.models import User


class BitpandaSnapshot(models.Model):
    """
    Speichert historische Snapshots des Bitpanda Portfolios
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='bitpanda_snapshots'
    )
    snapshot_date = models.DateTimeField(auto_now_add=True)

    # Portfolio Werte in EUR
    total_crypto_value_eur = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )
    total_fiat_value_eur = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )
    total_commodities_value_eur = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Gold, Silber, etc."
    )

    # Gesamtwert
    total_value_eur = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    # Raw JSON Daten als Backup
    raw_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Raw API Response für Debugging"
    )

    class Meta:
        verbose_name = "Bitpanda Snapshot"
        verbose_name_plural = "Bitpanda Snapshots"
        ordering = ['-snapshot_date']

    def __str__(self):
        return f"{self.user.username} - {self.snapshot_date.strftime('%Y-%m-%d %H:%M')} - €{self.total_value_eur}"