# finance/management/commands/berechne_stueckpreise.py
from django.core.management.base import BaseCommand
from finance.models import BillaArtikel


class Command(BaseCommand):
    help = 'Berechnet preis_pro_einheit für alle bestehenden Artikel'

    def handle(self, *args, **options):
        artikel = BillaArtikel.objects.all()
        count = 0

        for item in artikel:
            if item.menge > 0:
                item.preis_pro_einheit = item.gesamtpreis / item.menge
            else:
                item.preis_pro_einheit = item.gesamtpreis
            item.save()
            count += 1

        self.stdout.write(
            self.style.SUCCESS(f'✅ {count} Artikel aktualisiert')
        )