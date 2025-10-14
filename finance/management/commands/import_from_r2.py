# finance/management/commands/import_r2_all.py
# NEUES Command - Funktioniert garantiert!

from django.core.management.base import BaseCommand
from django.db import transaction
import tempfile
import os
import boto3

from finance.storages.r2_storage import CloudflareR2Storage
from finance.billa_parser import BillaReceiptParser
from finance.views_billa import _create_einkauf_with_artikel
from finance.models import BillaEinkauf


class Command(BaseCommand):
    help = 'Importiert ALLE Billa-PDFs von R2 (rekursiv, boto3-basiert)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--prefix',
            type=str,
            default='',
            help='Ordner/Prefix (z.B. "2025/01/")'
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
            help='Maximal zu importierende PDFs'
        )

    def handle(self, *args, **options):
        prefix = options['prefix']
        force = options['force']
        limit = options['limit']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('☁️  R2 Import (boto3-basiert)'))
        self.stdout.write('=' * 70)

        try:
            storage = CloudflareR2Storage()

            self.stdout.write(f'\n📦 Bucket: {storage.bucket_name}')
            self.stdout.write(f'📁 Prefix: {prefix or "(alle)"}')

            # Verwende boto3 direkt für zuverlässiges Listing
            self.stdout.write(f'\n🔍 Suche PDFs...')

            s3_client = boto3.client(
                's3',
                endpoint_url=storage.endpoint_url,
                aws_access_key_id=storage.access_key,
                aws_secret_access_key=storage.secret_key,
                region_name='auto'
            )

            # Liste alle Objekte mit Prefix
            paginator = s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(
                Bucket=storage.bucket_name,
                Prefix=prefix
            )

            # Sammle alle PDFs
            pdf_files = []
            for page in page_iterator:
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    if key.lower().endswith('.pdf'):
                        pdf_files.append(key)

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
            for idx, pdf_key in enumerate(pdf_files, 1):
                self.stdout.write(
                    f'[{idx:3d}/{len(pdf_files)}] {pdf_key}',
                    ending=''
                )

                try:
                    # Download zu temp file
                    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                        # Download von R2
                        s3_client.download_fileobj(
                            Bucket=storage.bucket_name,
                            Key=pdf_key,
                            Fileobj=temp_file
                        )
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
                    error_msg = str(e)[:80]
                    stats['error_details'].append({
                        'file': pdf_key,
                        'error': str(e)
                    })
                    self.stdout.write(self.style.ERROR(f' ✗ {error_msg}'))

            # Zusammenfassung
            self.stdout.write('\n' + '=' * 70)
            self.stdout.write(f'✓ Importiert: {stats["imported"]}')
            self.stdout.write(f'⊘ Übersprungen: {stats["skipped"]}')
            self.stdout.write(f'✗ Fehler: {stats["errors"]}')

            if stats['error_details'] and stats['errors'] <= 5:
                self.stdout.write('\n📋 Fehlerhafte Dateien:')
                for error in stats['error_details']:
                    self.stdout.write(f'   • {error["file"]}')
                    self.stdout.write(f'     → {error["error"][:100]}')

            self.stdout.write('=' * 70)

            # Erfolgs-Hinweis
            if stats['imported'] > 0:
                self.stdout.write('\n💡 Prüfe Ergebnis:')
                self.stdout.write('   python manage.py billa_info')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Fehler: {str(e)}'))
            raise