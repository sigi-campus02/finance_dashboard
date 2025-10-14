# finance/migrations/0008_change_filiale_to_foreignkey.py

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0011_billa_filialen'),
    ]

    operations = [
        # Schritt 1: Temporäre Spalte hinzufügen
        migrations.AddField(
            model_name='billaeinkauf',
            name='filiale_fk',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='finance.billafiliale',
                verbose_name='Filiale',
                related_name='einkauefe'
            ),
        ),

        # Schritt 2: Daten migrieren (alte CharField-Werte in neue ForeignKey)
        migrations.RunPython(
            code=lambda apps, schema_editor: migrate_filiale_data(apps, schema_editor),
            reverse_code=migrations.RunPython.noop
        ),

        # Schritt 3: Alte Spalte entfernen
        migrations.RemoveField(
            model_name='billaeinkauf',
            name='filiale',
        ),

        # Schritt 4: Neue Spalte umbenennen
        migrations.RenameField(
            model_name='billaeinkauf',
            old_name='filiale_fk',
            new_name='filiale',
        ),

        # Schritt 5: Null-Constraint entfernen (ForeignKey ist jetzt required)
        migrations.AlterField(
            model_name='billaeinkauf',
            name='filiale',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to='finance.billafiliale',
                verbose_name='Filiale',
                related_name='einkauefe'
            ),
        ),

        # Bonus: Index hinzufügen
        migrations.AddIndex(
            model_name='billaeinkauf',
            index=models.Index(fields=['filiale'], name='billa_einka_filiale_idx'),
        ),
    ]


def migrate_filiale_data(apps, schema_editor):
    """Migriert die alten filiale CharField-Werte zu ForeignKey-Referenzen"""
    BillaEinkauf = apps.get_model('finance', 'BillaEinkauf')
    BillaFiliale = apps.get_model('finance', 'BillaFiliale')

    # Alle Einkäufe durchgehen und ForeignKey setzen
    for einkauf in BillaEinkauf.objects.all():
        try:
            filiale = BillaFiliale.objects.get(filial_nr=einkauf.filiale)
            einkauf.filiale_fk = filiale
            einkauf.save(update_fields=['filiale_fk'])
        except BillaFiliale.DoesNotExist:
            print(f"Warnung: Filiale {einkauf.filiale} nicht gefunden für Einkauf {einkauf.id}")
            # Optional: Hier kannst du eine Default-Filiale setzen oder einen Fehler werfen