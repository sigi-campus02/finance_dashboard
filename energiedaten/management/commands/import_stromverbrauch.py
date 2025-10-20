from datetime import datetime, date
from decimal import Decimal, InvalidOperation

import pandas as pd
from django.core.management.base import BaseCommand

from energiedaten.models import Stromverbrauch


class Command(BaseCommand):
    help = 'Importiert Stromverbrauchsdaten aus CSV- oder Excel-Datei (Tageswerte)'

    def add_arguments(self, parser):
        parser.add_argument('input_file', type=str, help='Pfad zur CSV- oder Excel-Datei')
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Überspringe bereits existierende Datensätze'
        )

    def handle(self, *args, **options):
        input_file = options['input_file']
        skip_existing = options['skip_existing']

        created_count = updated_count = skipped_count = error_count = 0

        self.stdout.write(f'📥 Importiere Daten aus: {input_file}')

        try:
            df = self._load_dataframe(input_file)
        except Exception as exc:  # pragma: no cover - defensive
            self.stdout.write(self.style.ERROR(f'❌ Fehler beim Öffnen der Datei: {exc}'))
            return

        for index, row in df.iterrows():
            try:
                datum = self._parse_date(row)
                verbrauch = self._parse_decimal(row)

                if skip_existing and Stromverbrauch.objects.filter(datum=datum).exists():
                    skipped_count += 1
                    continue

                _, created = Stromverbrauch.objects.update_or_create(
                    datum=datum,
                    defaults={'verbrauch_kwh': verbrauch}
                )

                if created:
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f'  ✓ {datum}: {verbrauch} kWh'))
                else:
                    updated_count += 1
            except ValueError as exc:
                self.stdout.write(self.style.ERROR(f'⚠️ Zeile {index + 2}: {exc}'))
                error_count += 1
            except Exception as exc:  # pragma: no cover - defensive
                self.stdout.write(self.style.ERROR(f'⚠️ Zeile {index + 2}: {exc}'))
                error_count += 1

        self.stdout.write(self.style.SUCCESS('\n✅ Import abgeschlossen!'))
        self.stdout.write(f'  Neu erstellt: {created_count}')
        if skip_existing:
            self.stdout.write(f'  Übersprungen: {skipped_count}')
        else:
            self.stdout.write(f'  Aktualisiert: {updated_count}')
        if error_count:
            self.stdout.write(self.style.WARNING(f'  ⚠ Fehler: {error_count}'))

    def _load_dataframe(self, input_file: str) -> pd.DataFrame:
        if input_file.lower().endswith(('.xls', '.xlsx')):
            return pd.read_excel(input_file)
        return pd.read_csv(input_file, delimiter=';', encoding='utf-8-sig')

    def _parse_date(self, row) -> date:
        value = row.get('Zeitstempel') if hasattr(row, 'get') else row['Zeitstempel']
        if pd.isna(value):
            raise ValueError('Kein Datum gefunden (Spalte "Zeitstempel")')

        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value

        value_str = str(value).strip()
        for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
            try:
                return datetime.strptime(value_str, fmt).date()
            except ValueError:
                continue

        raise ValueError(f'Unerkanntes Datumsformat: "{value_str}"')

    def _parse_decimal(self, row) -> Decimal:
        value = row.get('Wert (kWh)') if hasattr(row, 'get') else row['Wert (kWh)']
        if pd.isna(value):
            raise ValueError('Kein Verbrauchswert gefunden (Spalte "Wert (kWh)")')

        if isinstance(value, (int, float)):
            return Decimal(str(value))

        value_str = str(value).strip().replace(',', '.')
        try:
            return Decimal(value_str)
        except InvalidOperation as exc:
            raise ValueError(f'Ungültiger Verbrauchswert: "{value_str}"') from exc
