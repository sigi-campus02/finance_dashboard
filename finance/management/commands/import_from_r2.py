# finance/management/commands/import_from_r2.py

from django.core.management.base import BaseCommand
from django.db import transaction
import tempfile
import os

from finance.storages.r2_storage import CloudflareR2Storage
from finance.billa_parser import BillaReceiptParser
from finance.views_billa import _create_einkauf_with_artikel
from finance.models import BillaEinkauf


class Command(BaseCommand):
    help = 'Importiert Billa-PDFs von Cloudflare R2 Storage'

    def add_arguments(self, parser):
        parser.add_argument(
            '--prefix',
            type=str,
            default='',
            help='Ordner/Prefix in R2 (z.B. "2025/" oder "billa_pdfs/")'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Überschreibt bereits importierte Rechnungen'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Maximal zu importierende PDFs (für Tests)'
        )

    def handle(self, *args, **options):
        prefix = options['prefix']
        force = options['force']
        limit = options['limit']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('☁️  Cloudflare R2 Import'))
        self.stdout.write('=' * 70)

        try:
            # Initialisiere R2 Storage
            storage = CloudflareR2Storage()

            self.stdout.write(f'\n📦 Bucket: {storage.bucket_name}')
            self.stdout.write(f'📁 Prefix: {prefix or "(root)"}')

            # Liste alle PDFs
            self.stdout.write(f'\n🔍 Suche PDFs...')

            directories, files = storage.listdir(prefix)
            pdf_files = [f for f in files if f.lower().endswith('.pdf')]

            if limit:
                pdf_files = pdf_files[:limit]
                self.stdout.write(f'⚠️  Limit aktiv: Nur {limit} PDFs')

            self.stdout.write(f'✓ Gefunden: {len(pdf_files)} PDFs\n')

            if not pdf_files:
                self.stdout.write(self.style.WARNING('Keine PDFs gefunden!'))
                return

            # Import-Statistiken
            stats = {
                'imported': 0,
                'skipped': 0,
                'errors': 0,
                'error_details': []
            }

            parser = BillaReceiptParser()

            # Importiere jedes PDF
            for idx, filename in enumerate(pdf_files, 1):
                self.stdout.write(
                    f'[{idx:3d}/{len(pdf_files)}] {filename}',
                    ending=''
                )

                try:
                    # Konstruiere vollständigen Pfad
                    r2_path = os.path.join(prefix, filename) if prefix else filename

                    # Download zu temp file
                    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                        # Lese von R2
                        with storage.open(r2_path, 'rb') as r2_file:
                            temp_file.write(r2_file.read())
                        temp_path = temp_file.name

                    try:
                        # Parse PDF
                        data = parser.parse_pdf(temp_path)

                        # Duplikat-Check
                        if not force and data.get('re_nr'):
                            if BillaEinkauf.objects.filter(re_nr=data['re_nr']).exists():
                                stats['skipped'] += 1
                                self.stdout.write(self.style.WARNING(' ⊘'))
                                continue

                        # Import in Transaktion
                        with transaction.atomic():
                            if force and data.get('re_nr'):
                                BillaEinkauf.objects.filter(re_nr=data['re_nr']).delete()

                            _create_einkauf_with_artikel(data)

                        stats['imported'] += 1
                        self.stdout.write(self.style.SUCCESS(' ✓'))

                    finally:
                        # Cleanup temp file
                        try:
                            os.unlink(temp_path)
                        except:
                            pass

                except Exception as e:
                    stats['errors'] += 1
                    stats['error_details'].append({
                        'file': filename,
                        'error': str(e)
                    })
                    self.stdout.write(self.style.ERROR(f' ✗ {str(e)[:50]}'))

            # Zusammenfassung
            self.stdout.write('\n' + '=' * 70)
            self.stdout.write(f'✓ Importiert: {stats["imported"]}')
            self.stdout.write(f'⊘ Übersprungen: {stats["skipped"]}')
            self.stdout.write(f'✗ Fehler: {stats["errors"]}')

            if stats['error_details']:
                self.stdout.write('\n📋 Fehlerhafte Dateien:')
                for error in stats['error_details'][:5]:  # Max 5 anzeigen
                    self.stdout.write(f'   • {error["file"]}: {error["error"][:60]}')

            self.stdout.write('=' * 70)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Fehler: {str(e)}'))

            # Hilfreiche Hinweise bei typischen Fehlern
            if 'credentials' in str(e).lower():
                self.stdout.write('\n💡 Hinweis: Prüfe deine R2 Environment Variables:')
                self.stdout.write('   R2_ACCESS_KEY_ID')
                self.stdout.write('   R2_SECRET_ACCESS_KEY')
                self.stdout.write('   R2_ENDPOINT_URL')

            raise