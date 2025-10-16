# billa/migrations/0002_add_name_korrigiert.py
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billa', '0001_initial'),
    ]

    operations = [
        # Schritt 1: Feld hinzufügen (nullable, damit es funktioniert)
        migrations.AddField(
            model_name='billaprodukt',
            name='name_korrigiert',
            field=models.CharField(
                max_length=500,
                null=True,
                blank=True,
                db_index=True,
                verbose_name='Korrigierter Name',
                help_text='Manuell korrigierter/vereinheitlichter Produktname'
            ),
        ),
    ]