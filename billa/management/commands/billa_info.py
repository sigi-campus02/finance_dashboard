# finance/management/commands/billa_info.py

from django.core.management.base import BaseCommand
from django.db.models import Sum, Avg, Count, Min, Max
from billa.models import (
    BillaEinkauf, BillaArtikel, BillaProdukt,
    BillaPreisHistorie, BillaFiliale
)


class Command(BaseCommand):
    help = 'Zeigt Informationen über die Billa-Daten in der Datenbank'

    def handle(self, *args, **options):
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('📊 Billa Datenbank-Übersicht'))
        self.stdout.write('=' * 70)

        # Filialen
        filialen = BillaFiliale.objects.all()
        self.stdout.write(f'\n🏪 Filialen: {filialen.count()}')
        if filialen.exists():
            for filiale in filialen.order_by('filial_nr'):
                einkauf_count = filiale.einkauefe.count()
                typ_icon = '🏬' if filiale.typ == 'billa_plus' else '🏪'
                aktiv = '✓' if filiale.aktiv else '✗'
                self.stdout.write(
                    f'   {typ_icon} [{aktiv}] {filiale.filial_nr} - {filiale.name} '
                    f'({einkauf_count} Einkäufe)'
                )

        # Einkäufe
        einkaufe = BillaEinkauf.objects.all()
        self.stdout.write(f'\n🛒 Einkäufe: {einkaufe.count():,}')

        if einkaufe.exists():
            stats = einkaufe.aggregate(
                gesamt_ausgaben=Sum('gesamt_preis'),
                gesamt_ersparnis=Sum('gesamt_ersparnis'),
                avg_warenkorb=Avg('gesamt_preis'),
                erster_einkauf=Min('datum'),
                letzter_einkauf=Max('datum')
            )

            self.stdout.write(f'   💰 Gesamtausgaben: € {stats["gesamt_ausgaben"]:,.2f}')
            self.stdout.write(f'   💸 Gesamt erspart: € {stats["gesamt_ersparnis"]:,.2f}')
            self.stdout.write(f'   🛍️  Ø Warenkorb: € {stats["avg_warenkorb"]:,.2f}')
            self.stdout.write(f'   📅 Zeitraum: {stats["erster_einkauf"]} bis {stats["letzter_einkauf"]}')

            # Top 5 Filialen
            top_filialen = (
                einkaufe
                .values('filiale__filial_nr', 'filiale__name')
                .annotate(
                    anzahl=Count('id'),
                    ausgaben=Sum('gesamt_preis')
                )
                .order_by('-anzahl')[:5]
            )

            self.stdout.write(f'\n   📍 Top 5 Filialen:')
            for idx, fil in enumerate(top_filialen, 1):
                self.stdout.write(
                    f'      {idx}. {fil["filiale__filial_nr"]} - {fil["filiale__name"]}: '
                    f'{fil["anzahl"]} Einkäufe (€ {fil["ausgaben"]:,.2f})'
                )

        # Artikel
        artikel = BillaArtikel.objects.all()
        self.stdout.write(f'\n📦 Artikel: {artikel.count():,}')

        if artikel.exists():
            artikel_stats = artikel.aggregate(
                gesamt_artikel=Count('id'),
                gesamt_wert=Sum('gesamtpreis'),
                gesamt_rabatt=Sum('rabatt')
            )
            self.stdout.write(f'   💶 Gesamtwert: € {artikel_stats["gesamt_wert"]:,.2f}')
            self.stdout.write(f'   🏷️  Gesamt Rabatt: € {artikel_stats["gesamt_rabatt"]:,.2f}')

        # Produkte
        produkte = BillaProdukt.objects.all()
        self.stdout.write(f'\n🏷️  Produkte: {produkte.count():,}')

        if produkte.exists():
            # Top 10 meist gekaufte Produkte
            top_produkte = (
                produkte
                .annotate(kaeufe=Count('artikel'))
                .filter(kaeufe__gt=0)
                .order_by('-kaeufe')[:10]
            )

            self.stdout.write(f'\n   🔥 Top 10 meist gekauft:')
            for idx, prod in enumerate(top_produkte, 1):
                marke = f' ({prod.marke})' if prod.marke else ''
                self.stdout.write(
                    f'      {idx:2d}. {prod.name_original}{marke}: '
                    f'{prod.kaeufe}x (€ {prod.letzter_preis:,.2f})'
                )

            # Produkte mit Marke
            mit_marke = produkte.exclude(marke__isnull=True).exclude(marke='').count()
            ohne_marke = produkte.filter(marke__isnull=True).count() + produkte.filter(marke='').count()
            self.stdout.write(f'\n   🏢 Mit Marke: {mit_marke:,} ({mit_marke / produkte.count() * 100:.1f}%)')
            self.stdout.write(f'   ❓ Ohne Marke: {ohne_marke:,} ({ohne_marke / produkte.count() * 100:.1f}%)')

        # Preishistorie
        historie = BillaPreisHistorie.objects.all()
        self.stdout.write(f'\n📈 Preishistorie: {historie.count():,} Einträge')

        # Verfügbare Commands
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS('🔧 Verfügbare Commands'))
        self.stdout.write('=' * 70)
        self.stdout.write('''
Daten importieren:
  python manage.py import_billa <pfad>              Import einzelner Dateien/Ordner
  python manage.py import_billa <pfad> --force      Überschreibt Duplikate

Batch-Import:
  python manage.py reimport_all_billa <verzeichnis>              Alle PDFs importieren
  python manage.py reimport_all_billa <verzeichnis> --reset      Mit Daten-Reset
  python manage.py reimport_all_billa <verzeichnis> --force      Duplikate überschreiben

Daten verwalten:
  python manage.py reset_billa_data                  Löscht Transaktionsdaten
  python manage.py reset_billa_data --keep-products  Behält Produkte
  python manage.py check_duplikate                   Zeigt Duplikate
  python manage.py check_duplikate --fix             Löscht Duplikate

Stammdaten:
  python manage.py update_filialen                   Aktualisiert Filialen-Namen
  python manage.py billa_info                        Diese Übersicht
''')

        self.stdout.write('=' * 70)