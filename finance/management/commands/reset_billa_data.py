# finance/management/commands/reset_billa_data.py

from django.core.management.base import BaseCommand
from finance.models import BillaEinkauf, BillaArtikel, BillaProdukt, BillaPreisHistorie, BillaKategorieMapping
from django.db import transaction


class Command(BaseCommand):
    help = 'Löscht alle Billa-Daten aus der Datenbank'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep-mappings',
            action='store_true',
            help='Behalte Kategorie-Mappings (werden nicht gelöscht)',
        )
        parser.add_argument(
            '--no-input',
            action='store_true',
            help='Keine Bestätigung erforderlich',
        )

    def handle(self, *args, **options):
        keep_mappings = options['keep_mappings']
        no_input = options['no_input']

        # Zähle vorhandene Daten
        einkauf_count = BillaEinkauf.objects.count()
        artikel_count = BillaArtikel.objects.count()
        produkt_count = BillaProdukt.objects.count()
        historie_count = BillaPreisHistorie.objects.count()
        mapping_count = BillaKategorieMapping.objects.count()

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.WARNING('⚠️  WARNUNG: Alle Billa-Daten werden gelöscht!'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'\n📊 Folgende Daten werden gelöscht:')
        self.stdout.write(f'   • {einkauf_count:,} Einkäufe')
        self.stdout.write(f'   • {artikel_count:,} Artikel')
        self.stdout.write(f'   • {produkt_count:,} Produkte')
        self.stdout.write(f'   • {historie_count:,} Preishistorie-Einträge')

        if not keep_mappings:
            self.stdout.write(f'   • {mapping_count:,} Kategorie-Mappings')
        else:
            self.stdout.write(f'   • {mapping_count:,} Kategorie-Mappings (BLEIBEN ERHALTEN)')

        if not no_input:
            self.stdout.write('\n' + '=' * 70)
            confirm = input('Möchtest du wirklich ALLE Daten löschen? (ja/nein): ')
            if confirm.lower() not in ['ja', 'yes', 'j', 'y']:
                self.stdout.write(self.style.ERROR('❌ Abgebrochen.'))
                return

        # Lösche Daten in der richtigen Reihenfolge (wegen Foreign Keys)
        try:
            with transaction.atomic():
                self.stdout.write('\n🗑️  Lösche Daten...')

                # 1. Preishistorie (hängt von Artikel und Produkt ab)
                deleted_historie = BillaPreisHistorie.objects.all().delete()
                self.stdout.write(f'   ✓ {deleted_historie[0]:,} Preishistorie-Einträge gelöscht')

                # 2. Artikel (hängt von Einkauf und Produkt ab)
                deleted_artikel = BillaArtikel.objects.all().delete()
                self.stdout.write(f'   ✓ {deleted_artikel[0]:,} Artikel gelöscht')

                # 3. Einkäufe
                deleted_einkauf = BillaEinkauf.objects.all().delete()
                self.stdout.write(f'   ✓ {deleted_einkauf[0]:,} Einkäufe gelöscht')

                # 4. Produkte
                deleted_produkt = BillaProdukt.objects.all().delete()
                self.stdout.write(f'   ✓ {deleted_produkt[0]:,} Produkte gelöscht')

                # 5. Optional: Kategorie-Mappings
                if not keep_mappings:
                    deleted_mappings = BillaKategorieMapping.objects.all().delete()
                    self.stdout.write(f'   ✓ {deleted_mappings[0]:,} Kategorie-Mappings gelöscht')

            self.stdout.write('\n' + '=' * 70)
            self.stdout.write(self.style.SUCCESS('✅ Alle Billa-Daten wurden erfolgreich gelöscht!'))
            self.stdout.write('=' * 70)
            self.stdout.write('\n💡 Jetzt kannst du die Rechnungen neu importieren:')
            self.stdout.write('   python manage.py reimport_all_billa\n')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Fehler beim Löschen: {str(e)}'))
            raise