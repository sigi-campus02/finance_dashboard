# finance/management/commands/r2_check.py
# Schnelle Übersicht über R2 Bucket

from django.core.management.base import BaseCommand
import boto3
from collections import defaultdict

from finance.storages.r2_storage import CloudflareR2Storage


class Command(BaseCommand):
    help = 'Zeigt schnelle Übersicht über R2 Bucket'

    def handle(self, *args, **options):
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('📦 R2 Bucket Check'))
        self.stdout.write('=' * 70)

        try:
            storage = CloudflareR2Storage()

            self.stdout.write(f'\n🔌 Bucket: {storage.bucket_name}')
            self.stdout.write('🔍 Scanne...\n')

            # Verwende boto3 für schnelles Listing
            s3_client = boto3.client(
                's3',
                endpoint_url=storage.endpoint_url,
                aws_access_key_id=storage.access_key,
                aws_secret_access_key=storage.secret_key,
                region_name='auto'
            )

            # Liste alle Objekte
            response = s3_client.list_objects_v2(Bucket=storage.bucket_name)

            if 'Contents' not in response:
                self.stdout.write(self.style.WARNING('⚠️  Bucket ist leer!'))
                return

            # Analysiere Struktur
            all_files = response.get('Contents', [])

            # Gruppiere nach Ordnern
            folders = defaultdict(list)
            total_pdfs = 0
            total_size = 0

            for obj in all_files:
                key = obj['Key']
                size = obj['Size']
                total_size += size

                if key.lower().endswith('.pdf'):
                    total_pdfs += 1

                    # Extrahiere Ordner
                    parts = key.split('/')
                    if len(parts) > 1:
                        folder = '/'.join(parts[:-1])
                        folders[folder].append({
                            'name': parts[-1],
                            'size': size
                        })
                    else:
                        folders['(root)'].append({
                            'name': key,
                            'size': size
                        })

            # Zeige Zusammenfassung
            self.stdout.write('📊 Zusammenfassung:')
            self.stdout.write(f'   Gesamt Dateien: {len(all_files)}')
            self.stdout.write(f'   PDFs: {total_pdfs}')
            self.stdout.write(f'   Größe: {self._format_size(total_size)}')

            # Zeige Ordner
            if folders:
                self.stdout.write(f'\n📁 Ordner mit PDFs: {len(folders)}\n')

                for folder in sorted(folders.keys()):
                    pdfs = folders[folder]
                    total_folder_size = sum(p['size'] for p in pdfs)

                    self.stdout.write(
                        f'   📁 {folder}/'
                    )
                    self.stdout.write(
                        f'      {len(pdfs)} PDFs ({self._format_size(total_folder_size)})'
                    )

                    # Zeige erste 2 PDFs
                    for pdf in sorted(pdfs, key=lambda x: x['name'])[:2]:
                        self.stdout.write(
                            f'         • {pdf["name"]} ({self._format_size(pdf["size"])})'
                        )

                    if len(pdfs) > 2:
                        self.stdout.write(f'         ... und {len(pdfs) - 2} weitere')

                    self.stdout.write('')

            # Import-Anweisungen
            self.stdout.write('=' * 70)
            self.stdout.write('💡 Import-Befehle:')
            self.stdout.write('=' * 70)

            if total_pdfs == 0:
                self.stdout.write('\n⚠️  Keine PDFs gefunden!')
                self.stdout.write('   Upload erst PDFs mit:')
                self.stdout.write('   python manage.py upload_to_r2 <pfad>')
            else:
                self.stdout.write('\n   # Alle PDFs importieren:')
                self.stdout.write('   python manage.py import_from_r2')

                if len(folders) > 1:
                    self.stdout.write('\n   # Aus spezifischem Ordner:')
                    for folder in sorted(folders.keys())[:3]:
                        if folder != '(root)':
                            self.stdout.write(f'   python manage.py import_from_r2 --prefix {folder}/')

                self.stdout.write('')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Fehler: {str(e)}'))
            raise

    def _format_size(self, bytes):
        """Formatiert Bytes human-readable"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes < 1024.0:
                return f"{bytes:.1f} {unit}"
            bytes /= 1024.0
        return f"{bytes:.1f} TB"