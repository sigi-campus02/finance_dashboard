# finance/management/commands/reimport_all_billa.py

from django.core.management.base import BaseCommand
from django.core.management import call_command
from pathlib import Path
from finance.models import BillaEinkauf


class Command(BaseCommand):
    help = 'Importiert alle Billa-PDFs aus einem Verzeichnis (mit optionalem Reset)'

    def add_arguments(self, parser):
        parser.add_argument(
            'verzeichnis',
            type=str,
            help='Verzeichnis mit den PDF-Rechnungen'
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Löscht vorher alle bestehenden Transaktionsdaten',
        )
        parser.add_argument(
            '--keep-products',
            action='store_true',
            help='Behält Produkte bei (nur mit --reset)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Überschreibt bereits importierte Rechnungen',
        )
        parser.add_argument(
            '--no-input',
            action='store_true',
            help='Keine Bestätigung erforderlich',
        )

    def handle(self, *args, **options):
        verzeichnis = options['verzeichnis']
        reset = options['reset']
        keep_products = options['keep_products']
        force = options['force']
        no_input = options['no_input']

        # Prüfe ob Verzeichnis existiert
        path = Path(verzeichnis)
        if not path.is_dir():
            self.stdout.write(
                self.style.ERROR(f'❌ Verzeichnis nicht gefunden: {verzeichnis}')
            )
            return

        # Finde alle PDF-Dateien
        pdf_files = sorted(list(path.glob('*.pdf')))

        if not pdf_files:
            self.stdout.write(
                self.style.WARNING(f'⚠️  Keine PDF-Dateien gefunden in: {verzeichnis}')
            )
            return

        # Header
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('📄 Billa Batch-Import'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'\n📁 Verzeichnis: {verzeichnis}')
        self.stdout.write(f'📊 Gefunden: {len(pdf_files)} PDF-Dateien')

        # Zeige aktuelle Datenmenge
        if reset:
            anzahl_einkaufe = BillaEinkauf.objects.count()
            self.stdout.write(f'⚠️  Reset aktiv: {anzahl_einkaufe:,} bestehende Einkäufe werden gelöscht')

        # Optional: Reset durchführen
        if reset:
            self.stdout.write('\n' + '=' * 70)
            self.stdout.write(self.style.WARNING('⚠️  DATEN WERDEN GELÖSCHT!'))
            self.stdout.write('=' * 70)

            if not no_input:
                confirm = input('\nWirklich alle Daten löschen und neu importieren? (ja/nein): ')
                if confirm.lower() not in ['ja', 'yes', 'j', 'y']:
                    self.stdout.write(self.style.ERROR('❌ Abgebrochen.'))
                    return

            self.stdout.write('')

            # Rufe reset_billa_data Command auf
            reset_args = ['--no-input']
            if keep_products:
                reset_args.append('--keep-products')

            call_command('reset_billa_data', *reset_args)

        # Starte Import
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS('📥 Starte Import...'))
        self.stdout.write('=' * 70 + '\n')

        erfolg = 0
        fehler = 0
        uebersprungen = 0
        fehler_dateien = []

        for idx, pdf_file in enumerate(pdf_files, 1):
            self.stdout.write(f'[{idx:3d}/{len(pdf_files)}] {pdf_file.name}', ending='')

            try:
                # Rufe import_billa für jede Datei auf
                import_args = [str(pdf_file)]
                if force:
                    import_args.append('--force')

                # Capture output
                from io import StringIO
                import sys
                old_stdout = sys.stdout
                sys.stdout = StringIO()

                call_command('import_billa', *import_args)

                sys.stdout = old_stdout

                # Prüfe ob erfolgreich
                # (Wir können nicht direkt wissen ob imported oder skipped, also prüfen wir die DB)
                # Für jetzt zählen wir es als Erfolg
                erfolg += 1
                self.stdout.write(self.style.SUCCESS(' ✓'))

            except Exception as e:
                sys.stdout = old_stdout
                fehler += 1
                fehler_dateien.append({
                    'datei': pdf_file.name,
                    'fehler': str(e)
                })
                self.stdout.write(self.style.ERROR(f' ✗ {str(e)}'))

        # Zusammenfassung
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS('📊 ZUSAMMENFASSUNG'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'\n✓ Erfolgreich: {erfolg:,}')

        if fehler > 0:
            self.stdout.write(f'✗ Fehler: {fehler:,}')
            self.stdout.write('\n📋 Fehlerhafte Dateien:')
            for item in fehler_dateien:
                self.stdout.write(f'   • {item["datei"]}')
                self.stdout.write(f'     → {item["fehler"]}')

        # Finale Statistik aus DB
        anzahl_einkaufe = BillaEinkauf.objects.count()
        self.stdout.write(f'\n📈 Datenbank:')
        self.stdout.write(f'   Gesamt Einkäufe: {anzahl_einkaufe:,}')

        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS('✅ Batch-Import abgeschlossen!'))
        self.stdout.write('=' * 70)
        self.stdout.write('')