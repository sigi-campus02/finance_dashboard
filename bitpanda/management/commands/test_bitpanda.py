# finance/management/commands/test_bitpanda.py
from django.core.management.base import BaseCommand
import os
import requests
from decimal import Decimal


class Command(BaseCommand):
    help = 'Testet die Bitpanda API Verbindung'

    def add_arguments(self, parser):
        parser.add_argument(
            '--api-key',
            type=str,
            help='Optionaler API Key zum Testen (überschreibt ENV Variable)'
        )

    def handle(self, *args, **options):
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('🔍 Bitpanda API Test'))
        self.stdout.write('=' * 70)

        # 1. Prüfe API Key
        self.stdout.write('\n📋 Environment Variable Check:')

        api_key = options.get('api_key') or os.environ.get('BITPANDA_API_KEY')

        if api_key:
            masked_key = f'{api_key[:8]}...{api_key[-4:]}' if len(api_key) > 12 else '***'
            self.stdout.write(self.style.SUCCESS(f'  ✓ BITPANDA_API_KEY: {masked_key}'))

            if options.get('api_key'):
                self.stdout.write('    ℹ️  Verwendet --api-key Parameter')
            else:
                self.stdout.write('    ℹ️  Verwendet Environment Variable')
        else:
            self.stdout.write(self.style.ERROR('  ✗ BITPANDA_API_KEY: NICHT GESETZT'))
            self.stdout.write('\n💡 Lösungsvorschläge:')
            self.stdout.write('   • Lokal: Setze in .env Datei')
            self.stdout.write('   • Render: Setze in Environment Variables')
            self.stdout.write('   • Test: Nutze --api-key Parameter')
            self.stdout.write('\nBeispiel:')
            self.stdout.write('   python manage.py test_bitpanda --api-key="dein_key_hier"')
            return

        # 2. Teste API Endpoints
        base_url = 'https://api.bitpanda.com/v1'
        headers = {
            'X-Api-Key': api_key,
            'Content-Type': 'application/json'
        }

        tests = [
            {
                'name': 'Crypto Wallets',
                'endpoint': '/wallets',
                'icon': '₿'
            },
            {
                'name': 'Fiat Wallets',
                'endpoint': '/fiatwallets',
                'icon': '💶'
            },
            {
                'name': 'Asset Wallets',
                'endpoint': '/asset-wallets',
                'icon': '📊'
            },
            {
                'name': 'Trades',
                'endpoint': '/trades',
                'icon': '📈'
            }
        ]

        results = {}

        for test in tests:
            self.stdout.write(f'\n{test["icon"]} Teste {test["name"]}...')

            try:
                response = requests.get(
                    f'{base_url}{test["endpoint"]}',
                    headers=headers,
                    timeout=10
                )

                if response.status_code == 200:
                    data = response.json()
                    results[test['name']] = {
                        'success': True,
                        'data': data
                    }
                    self.stdout.write(self.style.SUCCESS('  ✓ Verbindung erfolgreich'))

                    # Zeige erste Ergebnisse
                    if 'data' in data:
                        if isinstance(data['data'], list):
                            count = len(data['data'])
                            self.stdout.write(f'    ℹ️  {count} Einträge gefunden')
                        elif isinstance(data['data'], dict):
                            self.stdout.write('    ℹ️  Daten empfangen')

                elif response.status_code == 401:
                    self.stdout.write(self.style.ERROR('  ✗ Ungültiger API Key (401)'))
                    results[test['name']] = {'success': False, 'error': 'Invalid API Key'}
                    break

                elif response.status_code == 403:
                    self.stdout.write(self.style.ERROR('  ✗ Keine Berechtigung (403)'))
                    results[test['name']] = {'success': False, 'error': 'Forbidden'}

                else:
                    self.stdout.write(self.style.ERROR(f'  ✗ Fehler: HTTP {response.status_code}'))
                    results[test['name']] = {'success': False, 'error': f'HTTP {response.status_code}'}

            except requests.exceptions.Timeout:
                self.stdout.write(self.style.ERROR('  ✗ Timeout (API nicht erreichbar)'))
                results[test['name']] = {'success': False, 'error': 'Timeout'}

            except requests.exceptions.ConnectionError:
                self.stdout.write(self.style.ERROR('  ✗ Verbindungsfehler'))
                results[test['name']] = {'success': False, 'error': 'Connection Error'}

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ Fehler: {str(e)}'))
                results[test['name']] = {'success': False, 'error': str(e)}

        # 3. Detaillierte Ergebnisse
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write('📊 Detaillierte Ergebnisse:')
        self.stdout.write('=' * 70)

        # Crypto Wallets
        if results.get('Crypto Wallets', {}).get('success'):
            self.stdout.write('\n₿ Crypto Wallets:')
            data = results['Crypto Wallets']['data'].get('data', [])

            if data:
                for wallet in data[:5]:  # Zeige max 5
                    attrs = wallet.get('attributes', {})
                    if not attrs.get('deleted', False):
                        symbol = attrs.get('cryptocoin_symbol', 'N/A')
                        balance = attrs.get('balance', '0')
                        name = attrs.get('name', 'N/A')
                        self.stdout.write(f'  • {symbol}: {balance} ({name})')

                if len(data) > 5:
                    self.stdout.write(f'  ... und {len(data) - 5} weitere')
            else:
                self.stdout.write('  (keine Wallets)')

        # Fiat Wallets
        if results.get('Fiat Wallets', {}).get('success'):
            self.stdout.write('\n💶 Fiat Wallets:')
            data = results['Fiat Wallets']['data'].get('data', [])

            total_eur = Decimal('0')

            if data:
                for wallet in data:
                    attrs = wallet.get('attributes', {})
                    symbol = attrs.get('fiat_symbol', 'N/A')
                    balance = attrs.get('balance', '0')
                    name = attrs.get('name', 'N/A')
                    self.stdout.write(f'  • {symbol}: {balance} ({name})')

                    if symbol == 'EUR':
                        total_eur += Decimal(balance)

                if total_eur > 0:
                    self.stdout.write(self.style.SUCCESS(f'\n  💰 Gesamt EUR: €{total_eur}'))
            else:
                self.stdout.write('  (keine Wallets)')

        # Trades
        if results.get('Trades', {}).get('success'):
            self.stdout.write('\n📈 Letzte Trades:')
            data = results['Trades']['data'].get('data', [])

            if data:
                for trade in data[:3]:  # Zeige max 3
                    attrs = trade.get('attributes', {})
                    trade_type = attrs.get('type', 'N/A')
                    amount = attrs.get('amount_fiat', 'N/A')
                    status = attrs.get('status', 'N/A')
                    time = attrs.get('time', {}).get('date_iso8601', 'N/A')
                    self.stdout.write(f'  • {trade_type.upper()}: €{amount} ({status}) - {time}')

                if len(data) > 3:
                    self.stdout.write(f'  ... und {len(data) - 3} weitere')
            else:
                self.stdout.write('  (keine Trades)')

        # 4. Zusammenfassung
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write('✅ Zusammenfassung:')
        self.stdout.write('=' * 70)

        success_count = sum(1 for r in results.values() if r.get('success'))
        total_count = len(results)

        if success_count == total_count:
            self.stdout.write(self.style.SUCCESS(f'\n🎉 Alle Tests bestanden! ({success_count}/{total_count})'))
            self.stdout.write('\nDu kannst jetzt die Bitpanda Integration nutzen:')
            self.stdout.write('  • Dashboard: /finance/bitpanda/')
            self.stdout.write('  • Sync: Klicke auf "Jetzt synchronisieren"')
        elif success_count > 0:
            self.stdout.write(self.style.WARNING(f'\n⚠️  Teilweise erfolgreich ({success_count}/{total_count})'))
        else:
            self.stdout.write(self.style.ERROR(f'\n❌ Alle Tests fehlgeschlagen ({success_count}/{total_count})'))
            self.stdout.write('\n💡 Überprüfe:')
            self.stdout.write('  • API Key korrekt?')
            self.stdout.write('  • Berechtigungen bei Bitpanda richtig gesetzt?')
            self.stdout.write('  • Internet-Verbindung?')

        self.stdout.write('\n' + '=' * 70)