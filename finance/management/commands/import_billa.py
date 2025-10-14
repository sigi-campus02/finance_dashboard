# finance/management/commands/import_billa.py

from django.core.management.base import BaseCommand
from django.db import transaction
from pathlib import Path

from finance.models import BillaEinkauf
from finance.billa_parser import BillaReceiptParser  # ← Importiere konsolidierte Klasse
from finance.views_billa import _create_einkauf_with_artikel  # ← Gemeinsame Logik


class Command(BaseCommand):
    help = 'Importiert Billa-Rechnungen aus PDF-Dateien'

    def add_arguments(self, parser):
        parser.add_argument(
            'pdf_path',
            type=str,
            help='Pfad zur PDF-Datei oder Verzeichnis mit PDFs'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Überschreibt existierende Rechnungen'
        )

    def handle(self, *args, **options):
        pdf_path = options['pdf_path']
        force = options['force']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('📄 Billa PDF Import'))
        self.stdout.write('=' * 70)

        path = Path(pdf_path)

        if path.is_file():
            pdf_files = [path]
        elif path.is_dir():
            pdf_files = list(path.glob('*.pdf'))
        else:
            self.stdout.write(self.style.ERROR(f'✗ Pfad nicht gefunden: {pdf_path}'))
            return

        stats = {
            'total': len(pdf_files),
            'imported': 0,
            'skipped': 0,
            'errors': 0
        }

        self.stdout.write(f'\n📁 {stats["total"]} PDF-Dateien gefunden\n')

        for pdf_file in pdf_files:
            try:
                result = self.import_pdf(str(pdf_file), force)
                if result:
                    stats['imported'] += 1
                    self.stdout.write(self.style.SUCCESS(f'✓ {pdf_file.name}'))
                else:
                    stats['skipped'] += 1
                    self.stdout.write(self.style.WARNING(f'⊘ {pdf_file.name} (bereits vorhanden)'))
            except Exception as e:
                stats['errors'] += 1
                self.stdout.write(self.style.ERROR(f'✗ {pdf_file.name}: {str(e)}'))

        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(f'✓ Importiert: {stats["imported"]}')
        self.stdout.write(f'⊘ Übersprungen: {stats["skipped"]}')
        self.stdout.write(f'✗ Fehler: {stats["errors"]}')
        self.stdout.write('=' * 70)

    @transaction.atomic
    def import_pdf(self, pdf_path, force=False):
        """Importiert eine einzelne PDF-Datei"""
        parser = BillaReceiptParser()
        data = parser.parse_pdf(pdf_path)

        # Prüfe ob bereits importiert
        if not force and data.get('re_nr'):
            if BillaEinkauf.objects.filter(re_nr=data['re_nr']).exists():
                return False

        # Bei force: Alte Rechnung löschen
        if force and data.get('re_nr'):
            alte_rechnung = BillaEinkauf.objects.filter(re_nr=data['re_nr']).first()
            if alte_rechnung:
                alte_rechnung.delete()

        # Verwende gemeinsame Logik (keine Duplizierung!)
        _create_einkauf_with_artikel(data)
        return True