from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('billa', '0006_create_kategorie_tables'),
    ]

    operations = [
        # Benenne alte CharField-Felder um
        migrations.RenameField(
            model_name='billaprodukt',
            old_name='ueberkategorie',
            new_name='ueberkategorie_alt',
        ),
        migrations.RenameField(
            model_name='billaprodukt',
            old_name='produktgruppe',
            new_name='produktgruppe_alt',
        ),
    ]