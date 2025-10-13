# finance/management/commands/reimport_all_billa.py

from django.core.management.base import BaseCommand
from django.core.management import call_command
import os
from pathlib import Path


class Command(BaseCommand):
    help = 'Importiert alle Billa-PDFs aus einem Verzeichnis neu'

    def add_arguments(self, parser):
        parser.add_argument(
            'verzeichnis',
            type=str,
            help='Verzeichnis mit den PDF-Rechnungen'
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Löscht vorher alle bestehenden Daten',
        )
        parser.add_argument(
            '--keep-mappings',
            action='store_true',
            help='Behält Kategorie-Mappings bei (nur mit --reset)',
        )

    def handle(self, *args, **options):
        verzeichnis = options['verzeichnis']
        reset = options['reset']
        keep_mappings = options['keep_mappings']

        # Prüfe ob Verzeichnis existiert
        if not os.path.isdir(verzeichnis):
            self.stdout.write(
                self.style.ERROR(f'❌ Verzeichnis nicht gefunden: {verzeichnis}')
            )
            return

        # Optional: Lösche bestehende Daten
        if reset:
            self.stdout.write('\n🗑️  Lösche bestehende Daten...\n')
            if keep_mappings:
                call_command('reset_billa_data', '--keep-mappings', '--no-input')
            else:
                call_command('reset_billa_data', '--no-input')
            self.stdout.write('')

        # Finde alle PDF-Dateien
        pdf_files = list(Path(verzeichnis).glob('*.pdf'))

        if not pdf_files:
            self.stdout.write(
                self.style.WARNING(f'⚠️  Keine PDF-Dateien gefunden in: {verzeichnis}')
            )
            return

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS(f'📄 Gefunden: {len(pdf_files)} PDF-Dateien'))
        self.stdout.write('=' * 70 + '\n')

        # Importiere alle PDFs
        erfolg = 0
        fehler = 0
        fehler_dateien = []

        for idx, pdf_file in enumerate(sorted(pdf_files), 1):
            self.stdout.write(f'[{idx}/{len(pdf_files)}] Importiere: {pdf_file.name}')

            try:
                call_command('import_billa', str(pdf_file), verbosity=0)
                self.stdout.write(self.style.SUCCESS(f'   ✓ Erfolgreich importiert\n'))
                erfolg += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'   ✗ Fehler: {str(e)}\n'))
                fehler += 1
                fehler_dateien.append((pdf_file.name, str(e)))

        # Zusammenfassung
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('📊 IMPORT ABGESCHLOSSEN'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'\n✅ Erfolgreich: {erfolg}/{len(pdf_files)}')

        if fehler > 0:
            self.stdout.write(self.style.ERROR(f'❌ Fehler: {fehler}/{len(pdf_files)}'))
            self.stdout.write('\n📋 Fehlerhafte Dateien:')
            for datei, grund in fehler_dateien:
                self.stdout.write(f'   • {datei}')
                self.stdout.write(f'     Grund: {grund}')

        self.stdout.write('')