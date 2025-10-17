from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('billa', '0005_billakategorie'),  # Ersetze mit deiner letzten Migration
    ]

    operations = [
        # Erstelle Überkategorie-Tabelle
        migrations.CreateModel(
            name='BillaUeberkategorie',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, unique=True)),
                ('icon', models.CharField(blank=True, max_length=50, null=True)),
                ('erstellt_am', models.DateTimeField(auto_now_add=True)),
                ('geaendert_am', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Überkategorie',
                'verbose_name_plural': 'Überkategorien',
                'ordering': ['name'],
            },
        ),
        # Erstelle Produktgruppe-Tabelle
        migrations.CreateModel(
            name='BillaProduktgruppe',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('erstellt_am', models.DateTimeField(auto_now_add=True)),
                ('geaendert_am', models.DateTimeField(auto_now=True)),
                ('ueberkategorie', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='produktgruppen', to='billa.billaueberkategorie')),
            ],
            options={
                'verbose_name': 'Produktgruppe',
                'verbose_name_plural': 'Produktgruppen',
                'ordering': ['ueberkategorie__name', 'name'],
                'unique_together': {('name', 'ueberkategorie')},
            },
        ),
    ]