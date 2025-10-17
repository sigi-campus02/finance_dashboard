from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('billa', '0007_rename_old_fields'),
    ]

    operations = [
        # Füge neue FK-Felder hinzu (nullable)
        migrations.AddField(
            model_name='billaprodukt',
            name='ueberkategorie',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='produkte',
                to='billa.billaueberkategorie'
            ),
        ),
        migrations.AddField(
            model_name='billaprodukt',
            name='produktgruppe',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='produkte',
                to='billa.billaproduktgruppe'
            ),
        ),
    ]