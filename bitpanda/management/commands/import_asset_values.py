# bitpanda/management/commands/import_asset_values.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from bitpanda.models import BitpandaHolding, BitpandaAssetValue
from decimal import Decimal
from datetime import datetime
import csv
import chardet  # Für automatische Encoding-Erkennung


class Command(BaseCommand):
    help = 'Importiert historische Asset-Transaktionen aus CSV'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Pfad zur CSV-Datei')
        parser.add_argument('--user', type=str, required=True, help='Username')
        parser.add_argument('--delimiter', type=str, default=',', help='CSV Delimiter (Standard: ,)')
        parser.add_argument('--encoding', type=str, default='auto',
                            help='Encoding (auto, utf-8, windows-1252, iso-8859-1)')

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        username = options['user']
        delimiter = options['delimiter']
        encoding = options['encoding']

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User {username} nicht gefunden!'))
            return

        # Auto-detect encoding
        if encoding == 'auto':
            with open(csv_file, 'rb') as f:
                raw_data = f.read()
                result = chardet.detect(raw_data)
                encoding = result['encoding']
                self.stdout.write(f'Erkanntes Encoding: {encoding} (Confidence: {result["confidence"]:.0%})')

        self.stdout.write(f'Importiere Asset-Transaktionen für User: {username}')
        self.stdout.write(f'CSV-Datei: {csv_file}')
        self.stdout.write(f'Encoding: {encoding}')

        imported = 0
        errors = 0

        try:
            with open(csv_file, 'r', encoding=encoding) as file:
                # Entferne BOM falls vorhanden
                content = file.read()
                if content.startswith('\ufeff'):
                    content = content[1:]

                reader = csv.DictReader(content.splitlines(), delimiter=delimiter)

                # Zeige erkannte Spalten
                self.stdout.write(f'Erkannte Spalten: {reader.fieldnames}')


                for row_num, row in enumerate(reader, start=2):
                    try:
                        # Erwartete Spalten: asset, date, price_per_unit (Pflicht)
                        # Optional: payed, units
                        asset_symbol = row.get('asset', '').strip()
                        date_str = row.get('date', '').strip()
                        price_str = row.get('price_per_unit', '').strip()
                        payed_str = row.get('payed', '').strip()
                        units_str = row.get('units', '').strip()

                        # Nur asset, date und price_per_unit sind Pflicht
                        if not all([asset_symbol, date_str, price_str]):
                            self.stdout.write(
                                self.style.WARNING(
                                    f'Zeile {row_num}: Fehlende Pflichtfelder (asset, date, price_per_unit) - übersprungen')
                            )
                            errors += 1
                            continue

                        # Hole oder erstelle Holding
                        holding, created = BitpandaHolding.objects.get_or_create(
                            user=user,
                            asset=asset_symbol,
                            defaults={
                                'asset_class': 'Unknown',
                                'balance': Decimal('0'),
                            }
                        )

                        if created:
                            self.stdout.write(
                                self.style.WARNING(f'Holding für {asset_symbol} wurde neu erstellt')
                            )

                        # Parse Datum
                        try:
                            date_obj = datetime.strptime(date_str, '%d.%m.%Y').date()
                        except ValueError:
                            try:
                                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                            except ValueError:
                                try:
                                    date_obj = datetime.strptime(date_str, '%d/%m/%Y').date()
                                except ValueError:
                                    self.stdout.write(
                                        self.style.WARNING(f'Zeile {row_num}: Ungültiges Datumsformat {date_str}')
                                    )
                                    errors += 1
                                    continue

                        # Parse Werte (Komma → Punkt)
                        price_per_unit = Decimal(price_str.replace(',', '.'))

                        # Optional: payed und units
                        payed = Decimal(payed_str.replace(',', '.')) if payed_str else None
                        units = Decimal(units_str.replace(',', '.')) if units_str else None

                        # Erstelle Transaktion
                        asset_value = BitpandaAssetValue.objects.create(
                            holding=holding,
                            date=date_obj,
                            payed=payed,
                            units=units,
                            price_per_unit=price_per_unit,
                        )

                        # Ausgabe
                        if units is not None:
                            action = 'Kauf' if units > 0 else 'Verkauf'
                            imported += 1
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'✓ {asset_symbol} - {date_obj} - {action}: '
                                    f'{abs(units)} Einheiten à €{price_per_unit}'
                                    f'{f" = €{abs(payed)}" if payed else ""}'
                                )
                            )
                        else:
                            imported += 1
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'✓ {asset_symbol} - {date_obj} - Preis: €{price_per_unit}'
                                )
                            )

                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'✗ Zeile {row_num}: Fehler - {str(e)}')
                        )
                        errors += 1


        except UnicodeDecodeError as e:
            self.stdout.write(
                self.style.ERROR(
                    f'Encoding-Fehler: {e}\n'
                    f'Versuche ein anderes Encoding mit --encoding:\n'
                    f'  --encoding windows-1252\n'
                    f'  --encoding iso-8859-1\n'
                    f'  --encoding latin1'
                )
            )
            return

        self.stdout.write(self.style.SUCCESS(f'\n=== Import abgeschlossen ==='))
        self.stdout.write(f'Importiert: {imported}')
        self.stdout.write(f'Fehler: {errors}')