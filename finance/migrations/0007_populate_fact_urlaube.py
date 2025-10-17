from django.db import migrations
from decimal import Decimal
from datetime import date


def insert_urlaube_data(apps, schema_editor):
    """Fügt die Urlaubsdaten ein"""
    FactUrlaube = apps.get_model('finance', 'FactUrlaube')

    urlaube = [
        {'datum': '2023-01-03', 'beschreibung': 'Bad Waltersdorf', 'gesamt': 1198.40, 'robert': 698.40, 'sigi': 500.00},
        {'datum': '2023-01-07', 'beschreibung': 'St. Lambrecht', 'gesamt': 1079.30, 'robert': 0.00, 'sigi': 1079.30},
        {'datum': '2023-05-20', 'beschreibung': 'Pressegersee', 'gesamt': 602.00, 'robert': 302.00, 'sigi': 300.00},
        {'datum': '2023-06-22', 'beschreibung': 'Kopenhagen', 'gesamt': 2503.70, 'robert': 1455.84, 'sigi': 1047.86},
        {'datum': '2023-07-23', 'beschreibung': 'Dachstein', 'gesamt': 314.00, 'robert': 135.00, 'sigi': 179.00},
        {'datum': '2023-08-12', 'beschreibung': 'Gesäuse', 'gesamt': 347.40, 'robert': 83.40, 'sigi': 264.00},
        {'datum': '2023-10-01', 'beschreibung': 'Hotel Schwarzalm', 'gesamt': 767.50, 'robert': 714.50, 'sigi': 53.00},
        {'datum': '2024-03-29', 'beschreibung': 'Bad Hofgastein', 'gesamt': 470.00, 'robert': 432.60, 'sigi': 37.40},
        {'datum': '2024-07-20', 'beschreibung': 'Hamburg', 'gesamt': 3552.15, 'robert': 3129.28, 'sigi': 422.87},
        {'datum': '2024-09-07', 'beschreibung': 'Trattlerhof', 'gesamt': 242.10, 'robert': 242.10, 'sigi': 0.00},
        {'datum': '2024-10-25', 'beschreibung': 'Pierer', 'gesamt': 1180.70, 'robert': 1180.70, 'sigi': 0.00},
        {'datum': '2025-03-27', 'beschreibung': 'Trattlerhof Chalet', 'gesamt': 1358.10, 'robert': 717.70,
         'sigi': 640.40},
        {'datum': '2025-07-12', 'beschreibung': 'Robbie Konzert Wien', 'gesamt': 527.74, 'robert': 140.70,
         'sigi': 387.04},
        {'datum': '2025-07-26', 'beschreibung': 'Kaprun - Tauern Spa', 'gesamt': 2048.10, 'robert': 1850.10,
         'sigi': 198.00},
    ]

    urlaube_objects = []
    for urlaub in urlaube:
        # Konvertiere String zu date Objekt
        datum_obj = date.fromisoformat(urlaub['datum'])

        urlaube_objects.append(
            FactUrlaube(
                datum=datum_obj,
                beschreibung=urlaub['beschreibung'],
                gesamt_ausgaben=Decimal(str(urlaub['gesamt'])),
                anteil_robert=Decimal(str(urlaub['robert'])),
                anteil_sigi=Decimal(str(urlaub['sigi']))
            )
        )

    FactUrlaube.objects.bulk_create(urlaube_objects)

    print(f"✓ {len(urlaube)} Urlaube erfolgreich eingefügt")


def remove_urlaube_data(apps, schema_editor):
    """Entfernt alle Urlaubsdaten (für Rollback)"""
    FactUrlaube = apps.get_model('finance', 'FactUrlaube')
    FactUrlaube.objects.all().delete()
    print("✓ Urlaube entfernt")


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0006_create_fact_urlaube_table'),
    ]

    operations = [
        migrations.RunPython(insert_urlaube_data, remove_urlaube_data),
    ]