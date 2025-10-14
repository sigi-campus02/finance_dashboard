# finance/management/commands/render_manage.py
# Spezielles Command für Render.com Operationen

from django.core.management.base import BaseCommand
from django.core.management import call_command
import os


class Command(BaseCommand):
    help = 'Render.com Management Operationen'

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            type=str,
            choices=[
                'reset',           # Reset Billa-Daten
                'info',            # Zeige Statistiken
                'check-db',        # Prüfe DB-Verbindung
                'setup',           # Initial Setup
                'duplikate',       # Duplikate bereinigen
            ],
            help='Aktion die ausgeführt werden soll'
        )
        parser.add_argument(
            '--no-input',
            action='store_true',
            help='Keine Bestätigung'
        )

    def handle(self, *args, **options):
        action = options['action']
        no_input = options['no_input']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('🚀 Render.com Management'))
        self.stdout.write('=' * 70)

        # Zeige Environment
        self.stdout.write(f'\n🌍 Environment:')
        self.stdout.write(f'   RENDER: {os.environ.get("RENDER", "No")}')
        self.stdout.write(f'   DATABASE_URL: {"✓ Set" if os.environ.get("DATABASE_URL") else "✗ Missing"}')
        self.stdout.write('')

        if action == 'check-db':
            self._check_database()

        elif action == 'reset':
            self._reset_data(no_input)

        elif action == 'info':
            self._show_info()

        elif action == 'setup':
            self._initial_setup(no_input)

        elif action == 'duplikate':
            self._fix_duplikate()

    def _check_database(self):
        """Prüft DB-Verbindung"""
        self.stdout.write('🔍 Prüfe Datenbankverbindung...\n')

        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                self.stdout.write(self.style.SUCCESS('✓ Datenbankverbindung OK'))

            # Zeige Tabellen
            from django.db import connection
            tables = connection.introspection.table_names()
            billa_tables = [t for t in tables if 'billa' in t.lower()]

            self.stdout.write(f'\n📊 Billa-Tabellen ({len(billa_tables)}):')
            for table in billa_tables:
                self.stdout.write(f'   • {table}')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Fehler: {str(e)}'))
            raise

    def _reset_data(self, no_input):
        """Reset Billa-Daten"""
        self.stdout.write('🗑️  Reset Billa-Daten...\n')

        args = ['--no-input'] if no_input else []
        call_command('reset_billa_data', *args)

        self.stdout.write(self.style.SUCCESS('\n✓ Reset abgeschlossen'))

    def _show_info(self):
        """Zeige Statistiken"""
        self.stdout.write('📊 Lade Statistiken...\n')
        call_command('billa_info')

    def _initial_setup(self, no_input):
        """Initial Setup für neue Render-Instanz"""
        self.stdout.write('⚙️  Initial Setup...\n')

        # 1. Check DB
        self._check_database()

        # 2. Migrations
        self.stdout.write('\n📦 Führe Migrations aus...')
        call_command('migrate', '--no-input')

        # 3. Filialen
        self.stdout.write('\n🏪 Erstelle Filialen...')
        call_command('update_filialen')

        # 4. Collectstatic (für Production)
        if os.environ.get('RENDER'):
            self.stdout.write('\n📁 Collectstatic...')
            call_command('collectstatic', '--no-input')

        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS('✅ Setup abgeschlossen!'))
        self.stdout.write('=' * 70)
        self.stdout.write('\n💡 Nächste Schritte:')
        self.stdout.write('   1. Gehe zu: https://deine-app.onrender.com/finance/billa/import/')
        self.stdout.write('   2. Upload deine PDFs')
        self.stdout.write('   3. Fertig!\n')

    def _fix_duplikate(self):
        """Duplikate bereinigen"""
        self.stdout.write('🔍 Suche Duplikate...\n')
        call_command('check_duplikate', '--fix')
        self.stdout.write(self.style.SUCCESS('\n✓ Duplikate bereinigt'))