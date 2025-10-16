# billa/migrations/0003_copy_name_normalisiert_to_korrigiert.py
from django.db import migrations


def copy_name_normalisiert_to_korrigiert(apps, schema_editor):
    """Kopiert name_normalisiert zu name_korrigiert für alle Produkte"""
    BillaProdukt = apps.get_model('billa', 'BillaProdukt')

    # Alle Produkte updaten
    produkte = BillaProdukt.objects.all()
    for produkt in produkte:
        produkt.name_korrigiert = produkt.name_normalisiert

    # Bulk update für Performance
    BillaProdukt.objects.bulk_update(produkte, ['name_korrigiert'], batch_size=1000)

    print(f"✓ {produkte.count()} Produkte aktualisiert")


def reverse_copy(apps, schema_editor):
    """Reverse: Setzt name_korrigiert auf NULL zurück"""
    BillaProdukt = apps.get_model('billa', 'BillaProdukt')
    BillaProdukt.objects.all().update(name_korrigiert=None)


class Migration(migrations.Migration):
    dependencies = [
        ('billa', '0002_add_name_korrigiert'),
    ]

    operations = [
        migrations.RunPython(copy_name_normalisiert_to_korrigiert, reverse_copy),
    ]