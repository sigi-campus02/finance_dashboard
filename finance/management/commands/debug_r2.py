# finance/management/commands/debug_r2.py
# Debug-Command für R2-Verbindung

from django.core.management.base import BaseCommand
import os
import boto3
from botocore.exceptions import ClientError


class Command(BaseCommand):
    help = 'Debuggt R2-Verbindung und zeigt Probleme an'

    def handle(self, *args, **options):
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('🔍 R2 Connection Debug'))
        self.stdout.write('=' * 70)

        # 1. Prüfe Environment Variables
        self.stdout.write('\n📋 Environment Variables:')

        env_vars = {
            'R2_ACCESS_KEY_ID': os.environ.get('R2_ACCESS_KEY_ID'),
            'R2_SECRET_ACCESS_KEY': os.environ.get('R2_SECRET_ACCESS_KEY'),
            'R2_BUCKET_NAME': os.environ.get('R2_BUCKET_NAME'),
            'R2_ENDPOINT_URL': os.environ.get('R2_ENDPOINT_URL'),
        }

        all_set = True
        for key, value in env_vars.items():
            if value:
                # Zeige nur ersten/letzten Teil von Secrets
                if 'KEY' in key:
                    display = f'{value[:8]}...{value[-4:]}' if len(value) > 12 else '***'
                else:
                    display = value
                self.stdout.write(f'  ✓ {key}: {display}')
            else:
                self.stdout.write(self.style.ERROR(f'  ✗ {key}: NICHT GESETZT'))
                all_set = False

        if not all_set:
            self.stdout.write(self.style.ERROR('\n❌ Nicht alle Environment Variables sind gesetzt!'))
            self.stdout.write('\nSetze sie in Render Dashboard:')
            self.stdout.write('  Dashboard → Service → Environment → Add Environment Variable')
            return

        # 2. Teste S3 Client
        self.stdout.write('\n🔌 Teste Verbindung...')

        try:
            s3_client = boto3.client(
                's3',
                endpoint_url=env_vars['R2_ENDPOINT_URL'],
                aws_access_key_id=env_vars['R2_ACCESS_KEY_ID'],
                aws_secret_access_key=env_vars['R2_SECRET_ACCESS_KEY'],
                region_name='auto'
            )

            self.stdout.write('  ✓ S3 Client erstellt')

            # 3. Liste alle Buckets
            self.stdout.write('\n📦 Verfügbare Buckets:')

            try:
                response = s3_client.list_buckets()
                buckets = response.get('Buckets', [])

                if buckets:
                    for bucket in buckets:
                        name = bucket['Name']
                        if name == env_vars['R2_BUCKET_NAME']:
                            self.stdout.write(self.style.SUCCESS(f'  ✓ {name} (DEIN BUCKET)'))
                        else:
                            self.stdout.write(f'  • {name}')
                else:
                    self.stdout.write(self.style.WARNING('  ⚠️  Keine Buckets gefunden!'))
                    self.stdout.write('     → Erstelle einen Bucket in Cloudflare Dashboard')

            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == 'NoSuchBucket':
                    self.stdout.write(self.style.ERROR(f'  ✗ Bucket nicht gefunden: {env_vars["R2_BUCKET_NAME"]}'))
                else:
                    self.stdout.write(self.style.ERROR(f'  ✗ Fehler beim Listen: {error_code}'))

            # 4. Teste spezifischen Bucket
            self.stdout.write(f'\n🎯 Teste Bucket: {env_vars["R2_BUCKET_NAME"]}')

            try:
                # HEAD Bucket (prüft Existenz)
                s3_client.head_bucket(Bucket=env_vars['R2_BUCKET_NAME'])
                self.stdout.write(self.style.SUCCESS('  ✓ Bucket existiert'))

                # Liste Objekte
                response = s3_client.list_objects_v2(
                    Bucket=env_vars['R2_BUCKET_NAME'],
                    MaxKeys=5
                )

                count = response.get('KeyCount', 0)
                self.stdout.write(f'  ✓ Zugriff erfolgreich ({count} Objekte sichtbar)')

                if count > 0:
                    self.stdout.write('\n📄 Erste Dateien im Bucket:')
                    for obj in response.get('Contents', [])[:5]:
                        self.stdout.write(f'    • {obj["Key"]} ({obj["Size"]} bytes)')

            except ClientError as e:
                error_code = e.response['Error']['Code']
                error_msg = e.response['Error']['Message']

                self.stdout.write(self.style.ERROR(f'\n❌ Fehler: {error_code}'))
                self.stdout.write(f'   {error_msg}')

                if error_code == 'NoSuchBucket':
                    self.stdout.write('\n💡 Lösungsvorschläge:')
                    self.stdout.write('   1. Prüfe Bucket-Name in Cloudflare Dashboard')
                    self.stdout.write('   2. Bucket-Name ist case-sensitive!')
                    self.stdout.write(f'   3. Dein gesetzter Name: {env_vars["R2_BUCKET_NAME"]}')
                    self.stdout.write('   4. Vergleiche mit Cloudflare (exakt gleich?)')

                elif error_code == 'AccessDenied':
                    self.stdout.write('\n💡 Lösungsvorschläge:')
                    self.stdout.write('   1. Prüfe API Token Permissions')
                    self.stdout.write('   2. Token braucht "Read & Write" auf diesem Bucket')
                    self.stdout.write('   3. Erstelle neuen Token wenn nötig')

                elif error_code == 'InvalidAccessKeyId':
                    self.stdout.write('\n💡 Lösungsvorschläge:')
                    self.stdout.write('   1. Access Key ID ist falsch')
                    self.stdout.write('   2. Erstelle neuen API Token')
                    self.stdout.write('   3. Update R2_ACCESS_KEY_ID in Render')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Unerwarteter Fehler: {str(e)}'))

            # Häufige Fehler
            if 'endpoint' in str(e).lower():
                self.stdout.write('\n💡 Problem mit Endpoint URL:')
                self.stdout.write('   Format: https://<account-id>.r2.cloudflarestorage.com')
                self.stdout.write('   Finde es in: Cloudflare → R2 → Bucket → Settings')

        # 5. Zusammenfassung
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write('📋 Nächste Schritte:')
        self.stdout.write('=' * 70)
        self.stdout.write('''
1. Gehe zu Cloudflare Dashboard → R2 → Buckets
2. Kopiere den EXAKTEN Bucket-Namen (case-sensitive!)
3. Update in Render: Dashboard → Environment → R2_BUCKET_NAME
4. Führe nochmal aus: python manage.py debug_r2
''')