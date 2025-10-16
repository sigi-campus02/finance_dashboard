# finance/management/commands/aktualisiere_preishistorie.py

from django.core.management.base import BaseCommand
from billa.models import BillaPreisHistorie, BillaArtikel


class Command(BaseCommand):
    help = 'Aktualisiert alle Preishistorie-Einträge auf Stückpreise'

    def handle(self, *args, **options):
        self.stdout.write('Aktualisiere Preishistorie...')

        # Alle Preishistorie-Einträge
        historie_eintraege = BillaPreisHistorie.objects.select_related('artikel').all()
        count = 0
        updated = 0

        for historie in historie_eintraege:
            artikel = historie.artikel

            # Berechne Stückpreis
            if artikel.menge > 0:
                stueckpreis = artikel.gesamtpreis / artikel.menge
            else:
                stueckpreis = artikel.gesamtpreis

            # Nur aktualisieren wenn unterschiedlich
            if historie.preis != stueckpreis:
                historie.preis = stueckpreis
                historie.save()
                updated += 1

            count += 1

            if count % 100 == 0:
                self.stdout.write(f'  {count} Einträge verarbeitet...')

        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Fertig! {count} Einträge verarbeitet, {updated} aktualisiert'
            )
        )