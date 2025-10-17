# management/commands/import_stromverbrauch.py
import csv
from datetime import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from energiedaten.models import Stromverbrauch

class Command(BaseCommand):
    help = 'Importiert Stromverbrauchsdaten aus CSV-Datei'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Pfad zur CSV-Datei')
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Überspringe bereits existierende Datensätze'
        )

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        skip_existing = options['skip_existing']

        created_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0

        self.stdout.write(f'Importiere Daten aus {csv_file}...')

        try:
            with open(csv_file, 'r', encoding='utf-8') as file:
                # CSV mit Semikolon als Delimiter
                reader = csv.DictReader(file, delimiter=';')

                for row_num, row in enumerate(reader, start=2):
                    try:
                        # Datum parsen (Format: DD.MM.YYYY)
                        datum_str = row['Zeitstempel'].strip()
                        datum = datetime.strptime(datum_str, '%d.%m.%Y').date()

                        # Wert parsen (deutsches Format mit Komma)
                        wert_str = row['Wert (kWh)'].strip().replace(',', '.')
                        verbrauch = Decimal(wert_str)

                        # Datensatz erstellen oder aktualisieren
                        obj, created = Stromverbrauch.objects.update_or_create(
                            datum=datum,
                            defaults={'verbrauch_kwh': verbrauch}
                        )

                        if created:
                            created_count += 1
                        elif not skip_existing:
                            updated_count += 1
                        else:
                            skipped_count += 1

                    except KeyError as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f'Zeile {row_num}: Fehlende Spalte {e}'
                            )
                        )
                        error_count += 1
                    except ValueError as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f'Zeile {row_num}: Ungültiges Format - {e}'
                            )
                        )
                        error_count += 1
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f'Zeile {row_num}: Unerwarteter Fehler - {e}'
                            )
                        )
                        error_count += 1

            # Zusammenfassung
            self.stdout.write(self.style.SUCCESS(
                f'\nImport abgeschlossen!'
            ))
            self.stdout.write(f'  Neu erstellt: {created_count}')
            if not skip_existing:
                self.stdout.write(f'  Aktualisiert: {updated_count}')
            else:
                self.stdout.write(f'  Übersprungen: {skipped_count}')
            if error_count > 0:
                self.stdout.write(self.style.WARNING(
                    f'  Fehler: {error_count}'
                ))

        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR(f'Datei nicht gefunden: {csv_file}')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Fehler beim Öffnen der Datei: {e}')
            )