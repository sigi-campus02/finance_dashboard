# bitpanda/management/commands/import_bitpanda_csv.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from bitpanda.models import BitpandaTransaction, BitpandaHolding
from decimal import Decimal
import csv
from datetime import datetime
from collections import defaultdict


class Command(BaseCommand):
    help = 'Importiert Bitpanda Transaktionen aus CSV'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Pfad zur CSV-Datei')
        parser.add_argument('--user', type=str, required=True, help='Username')
        parser.add_argument('--clear', action='store_true', help='Lösche existierende Transaktionen vor Import')

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        username = options['user']
        clear = options.get('clear', False)

        # User holen
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User "{username}" nicht gefunden!'))
            return

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('📊 Bitpanda CSV Import'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'\nUser: {username}')
        self.stdout.write(f'Datei: {csv_file}')

        # Optional: Alte Daten löschen
        if clear:
            deleted_count = BitpandaTransaction.objects.filter(user=user).delete()[0]
            BitpandaHolding.objects.filter(user=user).delete()
            self.stdout.write(self.style.WARNING(f'\n🗑️  {deleted_count} alte Transaktionen gelöscht'))

        # CSV lesen
        transactions = []
        skipped = 0

        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                # CSV mit Semikolon-Trenner
                reader = csv.DictReader(f, delimiter=';')

                for row in reader:
                    try:
                        transaction = self._parse_row(row, user)
                        transactions.append(transaction)
                    except Exception as e:
                        skipped += 1
                        self.stdout.write(self.style.WARNING(f'⚠️  Zeile übersprungen: {e}'))

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'\n❌ Datei nicht gefunden: {csv_file}'))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Fehler beim Lesen: {e}'))
            return

        # Bulk Create (schneller)
        self.stdout.write(f'\n📥 Importiere {len(transactions)} Transaktionen...')

        created_count = 0
        duplicate_count = 0

        for transaction in transactions:
            try:
                transaction.save()
                created_count += 1
            except Exception as e:
                # Duplikat oder anderer Fehler
                duplicate_count += 1

        self.stdout.write(self.style.SUCCESS(f'\n✅ Import abgeschlossen!'))
        self.stdout.write(f'   • Erstellt: {created_count}')
        self.stdout.write(f'   • Duplikate: {duplicate_count}')
        self.stdout.write(f'   • Übersprungen: {skipped}')

        # Berechne Holdings
        self.stdout.write(f'\n📊 Berechne Bestände...')
        self._calculate_holdings(user)

        self.stdout.write(self.style.SUCCESS('\n🎉 Fertig!'))

    def _parse_row(self, row, user):
        """
        Parsed eine CSV-Zeile zu einem Transaction Objekt
        """
        from django.utils import timezone as tz

        # Datum parsen (Format: DD.MM.YYYY)
        timestamp = datetime.strptime(row['Timestamp'], '%d.%m.%Y')

        # Mache timezone-aware (Django nutzt Settings.TIME_ZONE)
        timestamp = tz.make_aware(timestamp)

        # Dezimalzahlen parsen (Komma → Punkt)
        def parse_decimal(value):
            if not value or value.strip() == '':
                return None
            # Ersetze Komma durch Punkt für Decimal
            return Decimal(value.replace(',', '.'))

        return BitpandaTransaction(
            user=user,
            transaction_id=row['Transaction ID'],
            timestamp=timestamp,
            transaction_type=row['Transaction Type'],
            direction=row['In/Out'],
            amount_fiat=parse_decimal(row['Amount Fiat']),
            fiat=row['Fiat'] or 'EUR',
            amount_asset=parse_decimal(row['Amount Asset']),
            asset=row['Asset'] if row['Asset'] else None,
            asset_market_price=parse_decimal(row['Asset market price']),
            asset_market_price_currency=row['Asset market price currency'] or 'EUR',
            asset_class=row['Asset class'] if row['Asset class'] else None,
            product_id=row['Product ID'] if row['Product ID'] else None,
            fee=parse_decimal(row['Fee']) or Decimal('0'),
            fee_asset=row['Fee asset'] if row['Fee asset'] else None,
            spread=parse_decimal(row['Spread']),
            spread_currency=row['Spread Currency'] if row['Spread Currency'] else None,
        )

    def _calculate_holdings(self, user):
        """
        Berechnet aktuelle Bestände aus allen Transaktionen
        """
        # Lösche alte Holdings
        BitpandaHolding.objects.filter(user=user).delete()

        # Gruppiere Transaktionen nach Asset
        holdings = defaultdict(lambda: {
            'balance': Decimal('0'),
            'total_bought': Decimal('0'),
            'total_spent': Decimal('0'),
            'asset_class': None,
        })

        transactions = BitpandaTransaction.objects.filter(user=user).order_by('timestamp')

        for tx in transactions:
            # Nur Asset-Transaktionen (nicht Fiat deposits/withdrawals)
            if not tx.asset:
                continue

            asset = tx.asset
            holdings[asset]['asset_class'] = tx.asset_class

            # Berechne Balance
            if tx.transaction_type == 'buy' and tx.amount_asset:
                holdings[asset]['balance'] += tx.amount_asset
                if tx.amount_fiat:
                    holdings[asset]['total_spent'] += tx.amount_fiat
                    holdings[asset]['total_bought'] += tx.amount_asset

            elif tx.transaction_type == 'sell' and tx.amount_asset:
                holdings[asset]['balance'] -= tx.amount_asset

            elif tx.transaction_type in ['transfer', 'deposit']:
                if tx.direction == 'incoming' and tx.amount_asset:
                    holdings[asset]['balance'] += tx.amount_asset
                elif tx.direction == 'outgoing' and tx.amount_asset:
                    holdings[asset]['balance'] -= tx.amount_asset

        # Erstelle Holding Objekte (nur für Assets mit Balance > 0)
        created = 0
        for asset, data in holdings.items():
            if data['balance'] > 0:
                # Durchschnittspreis berechnen
                avg_price = None
                if data['total_bought'] > 0:
                    avg_price = data['total_spent'] / data['total_bought']

                BitpandaHolding.objects.create(
                    user=user,
                    asset=asset,
                    asset_class=data['asset_class'],
                    balance=data['balance'],
                    average_buy_price=avg_price,
                    total_invested=data['total_spent'],
                )
                created += 1

        self.stdout.write(self.style.SUCCESS(f'   ✓ {created} Bestände berechnet'))