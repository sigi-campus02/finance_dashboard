# finance/management/commands/reset_billa_data.py

from django.core.management.base import BaseCommand
from django.db import transaction
from billa.models import (
    BillaEinkauf, BillaArtikel, BillaProdukt,
    BillaPreisHistorie, BillaFiliale
)


class Command(BaseCommand):
    help = 'Löscht alle Billa-Transaktionsdaten (behält Filialen-Stammdaten)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep-products',
            action='store_true',
            help='Behalte Produkte (nur Einkäufe/Artikel/Historie löschen)',
        )
        parser.add_argument(
            '--delete-filialen',
            action='store_true',
            help='ACHTUNG: Löscht auch Filialen-Stammdaten!',
        )
        parser.add_argument(
            '--no-input',
            action='store_true',
            help='Keine Bestätigung erforderlich',
        )

    def handle(self, *args, **options):
        keep_products = options['keep_products']
        delete_filialen = options['delete_filialen']
        no_input = options['no_input']

        # Zähle vorhandene Daten
        einkauf_count = BillaEinkauf.objects.count()
        artikel_count = BillaArtikel.objects.count()
        produkt_count = BillaProdukt.objects.count()
        historie_count = BillaPreisHistorie.objects.count()
        filiale_count = BillaFiliale.objects.count()

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.WARNING('⚠️  WARNUNG: Billa-Daten werden gelöscht!'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'\n📊 Folgende Daten werden gelöscht:')
        self.stdout.write(f'   • {einkauf_count:,} Einkäufe')
        self.stdout.write(f'   • {artikel_count:,} Artikel')
        self.stdout.write(f'   • {historie_count:,} Preishistorie-Einträge')

        if keep_products:
            self.stdout.write(f'   • {produkt_count:,} Produkte (BLEIBEN ERHALTEN)')
        else:
            self.stdout.write(f'   • {produkt_count:,} Produkte')

        if delete_filialen:
            self.stdout.write(self.style.ERROR(f'   • {filiale_count:,} Filialen (STAMMDATEN!)'))
        else:
            self.stdout.write(f'   • {filiale_count:,} Filialen (BLEIBEN ERHALTEN)')

        # Warnung wenn Filialen gelöscht werden sollen
        if delete_filialen:
            self.stdout.write('\n' + self.style.ERROR('⚠️  ACHTUNG: Du hast --delete-filialen gesetzt!'))
            self.stdout.write(self.style.ERROR('    Filialen sind Stammdaten und sollten normalerweise'))
            self.stdout.write(self.style.ERROR('    NICHT gelöscht werden!'))

        if not no_input:
            self.stdout.write('\n' + '=' * 70)
            if delete_filialen:
                confirm = input('⚠️  Wirklich ALLES inkl. Filialen löschen? (LÖSCHE ALLES/nein): ')
                if confirm != 'LÖSCHE ALLES':
                    self.stdout.write(self.style.ERROR('❌ Abgebrochen.'))
                    return
            else:
                confirm = input('Möchtest du die Transaktionsdaten löschen? (ja/nein): ')
                if confirm.lower() not in ['ja', 'yes', 'j', 'y']:
                    self.stdout.write(self.style.ERROR('❌ Abgebrochen.'))
                    return

        # Lösche Daten in der richtigen Reihenfolge (wegen Foreign Keys)
        try:
            with transaction.atomic():
                self.stdout.write('\n🗑️  Lösche Daten...\n')

                deleted_counts = {}

                # 1. Preishistorie (hängt von Artikel, Produkt und Filiale ab)
                deleted_historie = BillaPreisHistorie.objects.all().delete()
                deleted_counts['historie'] = deleted_historie[0]
                self.stdout.write(
                    self.style.SUCCESS(f'   ✓ {deleted_historie[0]:,} Preishistorie-Einträge gelöscht')
                )

                # 2. Artikel (hängt von Einkauf und Produkt ab)
                deleted_artikel = BillaArtikel.objects.all().delete()
                deleted_counts['artikel'] = deleted_artikel[0]
                self.stdout.write(
                    self.style.SUCCESS(f'   ✓ {deleted_artikel[0]:,} Artikel gelöscht')
                )

                # 3. Einkäufe (hängt von Filiale ab)
                deleted_einkauf = BillaEinkauf.objects.all().delete()
                deleted_counts['einkauf'] = deleted_einkauf[0]
                self.stdout.write(
                    self.style.SUCCESS(f'   ✓ {deleted_einkauf[0]:,} Einkäufe gelöscht')
                )

                # 4. Optional: Produkte löschen
                if not keep_products:
                    deleted_produkt = BillaProdukt.objects.all().delete()
                    deleted_counts['produkt'] = deleted_produkt[0]
                    self.stdout.write(
                        self.style.SUCCESS(f'   ✓ {deleted_produkt[0]:,} Produkte gelöscht')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'   ⊘ {produkt_count:,} Produkte beibehalten')
                    )

                # 5. Optional: Filialen löschen (NUR wenn explizit gewünscht!)
                if delete_filialen:
                    deleted_filialen = BillaFiliale.objects.all().delete()
                    deleted_counts['filialen'] = deleted_filialen[0]
                    self.stdout.write(
                        self.style.ERROR(f'   ✗ {deleted_filialen[0]:,} Filialen gelöscht')
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(f'   ✓ {filiale_count:,} Filialen beibehalten (Stammdaten)')
                    )

            # Zusammenfassung
            self.stdout.write('\n' + '=' * 70)
            self.stdout.write(self.style.SUCCESS('✅ Billa-Daten erfolgreich gelöscht!'))
            self.stdout.write('=' * 70)

            total_deleted = sum(deleted_counts.values())
            self.stdout.write(f'\n📊 Zusammenfassung:')
            self.stdout.write(f'   Gesamt gelöscht: {total_deleted:,} Datensätze')

            if not delete_filialen:
                self.stdout.write(f'   Filialen behalten: {filiale_count:,}')

            if keep_products:
                self.stdout.write(f'   Produkte behalten: {produkt_count:,}')

            self.stdout.write('\n💡 Nächste Schritte:')
            if delete_filialen:
                self.stdout.write('   1. Filialen neu anlegen:')
                self.stdout.write('      python manage.py update_filialen')
                self.stdout.write('   2. Rechnungen importieren:')
                self.stdout.write('      python manage.py import_billa /pfad/zu/pdfs/')
            else:
                self.stdout.write('   Rechnungen neu importieren:')
                self.stdout.write('   python manage.py import_billa /pfad/zu/pdfs/')

            self.stdout.write('')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Fehler beim Löschen: {str(e)}'))
            self.stdout.write(self.style.ERROR('   Transaktion wurde zurückgerollt.'))
            raise