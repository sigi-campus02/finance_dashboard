# finance/management/commands/upload_to_r2.py

from django.core.management.base import BaseCommand
from pathlib import Path
import os

from finance.storages.r2_storage import CloudflareR2Storage


class Command(BaseCommand):
    help = 'Uploaded Billa-PDFs von lokal zu Cloudflare R2'

    def add_arguments(self, parser):
        parser.add_argument(
            'source',
            type=str,
            help='Lokaler Pfad (Datei oder Verzeichnis)'
        )
        parser.add_argument(
            '--prefix',
            type=str,
            default='',
            help='Ziel-Ordner in R2 (z.B. "2025/")'
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Überschreibt vorhandene Dateien'
        )

    def handle(self, *args, **options):
        source = options['source']
        prefix = options['prefix']
        overwrite = options['overwrite']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('☁️  Upload zu Cloudflare R2'))
        self.stdout.write('=' * 70)

        # Prüfe Quelle
        source_path = Path(source)
        if not source_path.exists():
            self.stdout.write(self.style.ERROR(f'\n❌ Pfad nicht gefunden: {source}'))
            return

        # Sammle PDFs
        if source_path.is_file():
            if not source_path.suffix.lower() == '.pdf':
                self.stdout.write(self.style.ERROR(f'\n❌ Keine PDF-Datei: {source}'))
                return
            pdf_files = [source_path]
        else:
            pdf_files = list(source_path.glob('*.pdf'))

        if not pdf_files:
            self.stdout.write(self.style.WARNING(f'\n⚠️  Keine PDFs gefunden in: {source}'))
            return

        self.stdout.write(f'\n📁 Quelle: {source}')
        self.stdout.write(f'📦 Ziel: R2 Bucket{" → " + prefix if prefix else ""}')
        self.stdout.write(f'📄 Gefunden: {len(pdf_files)} PDFs\n')

        try:
            # Initialisiere R2 Storage
            storage = CloudflareR2Storage()

            stats = {
                'uploaded': 0,
                'skipped': 0,
                'errors': 0
            }

            for idx, pdf_file in enumerate(pdf_files, 1):
                self.stdout.write(
                    f'[{idx:3d}/{len(pdf_files)}] {pdf_file.name}',
                    ending=''
                )

                try:
                    # Ziel-Pfad in R2
                    r2_path = os.path.join(prefix, pdf_file.name) if prefix else pdf_file.name

                    # Prüfe ob bereits existiert
                    if not overwrite and storage.exists(r2_path):
                        stats['skipped'] += 1
                        self.stdout.write(self.style.WARNING(' ⊘ (existiert)'))
                        continue

                    # Upload
                    with open(pdf_file, 'rb') as f:
                        storage.save(r2_path, f)

                    stats['uploaded'] += 1
                    self.stdout.write(self.style.SUCCESS(' ✓'))

                except Exception as e:
                    stats['errors'] += 1
                    self.stdout.write(self.style.ERROR(f' ✗ {str(e)[:50]}'))

            # Zusammenfassung
            self.stdout.write('\n' + '=' * 70)
            self.stdout.write(f'✓ Hochgeladen: {stats["uploaded"]}')
            self.stdout.write(f'⊘ Übersprungen: {stats["skipped"]}')
            self.stdout.write(f'✗ Fehler: {stats["errors"]}')
            self.stdout.write('=' * 70)

            if stats['uploaded'] > 0:
                self.stdout.write('\n💡 Jetzt auf Render importieren:')
                self.stdout.write(f'   python manage.py import_from_r2 --prefix {prefix}')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Fehler: {str(e)}'))
            raise