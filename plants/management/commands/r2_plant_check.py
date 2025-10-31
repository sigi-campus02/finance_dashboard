# plants/management/commands/r2_plant_check.py
# Erstelle zuerst: plants/management/__init__.py (leer)
# Erstelle dann: plants/management/commands/__init__.py (leer)

from django.core.management.base import BaseCommand
import boto3
from collections import defaultdict

from plants.storage import PlantPhotoStorage


class Command(BaseCommand):
    help = 'Überprüft R2 Bucket für Pflanzenfotos'

    def handle(self, *args, **options):
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('🌱 Plant Photos R2 Bucket Check'))
        self.stdout.write('=' * 70)

        try:
            storage = PlantPhotoStorage()

            self.stdout.write(f'\n🔌 Bucket: {storage.bucket_name}')
            self.stdout.write(f'🌐 Endpoint: {storage.endpoint_url}')

            # Public URL wenn gesetzt
            if hasattr(storage, 'custom_domain'):
                self.stdout.write(f'🔗 Public URL: https://{storage.custom_domain}')

            self.stdout.write('\n🔍 Scanne Bucket...\n')

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

            # Statistiken sammeln
            objects = response['Contents']
            total_size = sum(obj['Size'] for obj in objects)

            # Nach Ordner gruppieren
            folders = defaultdict(lambda: {'count': 0, 'size': 0})

            for obj in objects:
                key = obj['Key']
                size = obj['Size']

                # Extrahiere Ordner (z.B. "plant_photos/plants/2025/01/")
                parts = key.split('/')
                if len(parts) > 1:
                    folder = '/'.join(parts[:-1])
                else:
                    folder = 'root'

                folders[folder]['count'] += 1
                folders[folder]['size'] += size

            # Ausgabe
            self.stdout.write(f'📊 Gesamt: {len(objects)} Dateien')
            self.stdout.write(f'💾 Größe: {self._format_size(total_size)}\n')

            # Details pro Ordner
            self.stdout.write(self.style.SUCCESS('📁 Ordner-Übersicht:'))
            for folder in sorted(folders.keys()):
                stats = folders[folder]
                self.stdout.write(
                    f'  {folder:50s} '
                    f'{stats["count"]:4d} Dateien  '
                    f'{self._format_size(stats["size"]):>10s}'
                )

            self.stdout.write('\n' + '=' * 70)
            self.stdout.write(self.style.SUCCESS('✅ R2 Bucket erfolgreich erreicht!'))

        except ValueError as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Konfigurationsfehler: {e}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Fehler: {e}'))

    def _format_size(self, bytes_size):
        """Formatiert Bytes in lesbare Größe"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} TB"