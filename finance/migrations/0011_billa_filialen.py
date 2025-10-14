# finance/migrations/0007_billa_filialen.py
# Diese Datei in deinem migrations-Ordner erstellen

from django.db import migrations, models


def insert_initial_filialen(apps, schema_editor):
    """Fügt die initialen Filialen-Daten ein"""
    BillaFiliale = apps.get_model('finance', 'BillaFiliale')

    filialen = [
        {
            'filial_nr': '06263',
            'name': 'Josef-Pock-Straße',
            'typ': 'billa_plus',
        },
        {
            'filial_nr': '06225',
            'name': 'Eggenberg',
            'typ': 'billa_plus',
        },
        {
            'filial_nr': '06703',
            'name': 'Shopping Nord',
            'typ': 'billa_plus',
        },
        {
            'filial_nr': '06816',
            'name': 'Körösistraße',
            'typ': 'billa',
        },
        {
            'filial_nr': '06521',
            'name': 'Anton-Kleinoscheg',
            'typ': 'billa',
        },
    ]

    for filiale_data in filialen:
        BillaFiliale.objects.create(**filiale_data)


def remove_filialen(apps, schema_editor):
    """Entfernt die Filialen-Daten (für Rollback)"""
    BillaFiliale = apps.get_model('finance', 'BillaFiliale')
    BillaFiliale.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0010_delete_billakategoriemapping_and_more'),
    ]

    operations = [
        # Erstelle die Tabelle
        migrations.CreateModel(
            name='BillaFiliale',
            fields=[
                ('filial_nr',
                 models.CharField(max_length=10, primary_key=True, serialize=False, verbose_name='Filial-Nummer')),
                ('name', models.CharField(max_length=200, verbose_name='Filialname')),
                ('typ', models.CharField(choices=[('billa', 'Billa'), ('billa_plus', 'Billa Plus')], max_length=20,
                                         verbose_name='Filialtyp')),
                ('adresse', models.CharField(blank=True, max_length=500, null=True, verbose_name='Adresse')),
                ('plz', models.CharField(blank=True, max_length=10, null=True, verbose_name='Postleitzahl')),
                ('ort', models.CharField(blank=True, max_length=100, null=True, verbose_name='Ort')),
                ('aktiv', models.BooleanField(default=True, verbose_name='Aktiv')),
            ],
            options={
                'verbose_name': 'Billa Filiale',
                'verbose_name_plural': 'Billa Filialen',
                'db_table': 'billa_filialen',
                'ordering': ['filial_nr'],
            },
        ),

        # Füge die initialen Daten ein
        migrations.RunPython(insert_initial_filialen, remove_filialen),
    ]