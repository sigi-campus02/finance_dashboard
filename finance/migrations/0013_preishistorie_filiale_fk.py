
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0012_change_filiale_to_foreignkey'),
    ]

    operations = [
        # Schritt 1: Temporäre Spalte
        migrations.AddField(
            model_name='billapreishistorie',
            name='filiale_fk',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='finance.billafiliale',
                verbose_name='Filiale',
                related_name='preishistorie_temp'
            ),
        ),

        # Schritt 2: Daten migrieren
        migrations.RunPython(
            code=lambda apps, schema_editor: migrate_preishistorie_filiale(apps, schema_editor),
            reverse_code=migrations.RunPython.noop
        ),

        # Schritt 3: Alte Spalte entfernen
        migrations.RemoveField(
            model_name='billapreishistorie',
            name='filiale',
        ),

        # Schritt 4: Umbenennen
        migrations.RenameField(
            model_name='billapreishistorie',
            old_name='filiale_fk',
            new_name='filiale',
        ),

        # Schritt 5: Null-Constraint entfernen
        migrations.AlterField(
            model_name='billapreishistorie',
            name='filiale',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to='finance.billafiliale',
                verbose_name='Filiale',
                related_name='preishistorie'
            ),
        ),
    ]


def migrate_preishistorie_filiale(apps, schema_editor):
    """Migriert die Preishistorie Filiale zu ForeignKey"""
    BillaPreisHistorie = apps.get_model('finance', 'BillaPreisHistorie')
    BillaFiliale = apps.get_model('finance', 'BillaFiliale')

    for historie in BillaPreisHistorie.objects.all():
        try:
            filiale = BillaFiliale.objects.get(filial_nr=historie.filiale)
            historie.filiale_fk = filiale
            historie.save(update_fields=['filiale_fk'])
        except BillaFiliale.DoesNotExist:
            print(f"Warnung: Filiale {historie.filiale} nicht gefunden")