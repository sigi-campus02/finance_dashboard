from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0005_facturlaube'),
    ]

    operations = [
        migrations.CreateModel(
            name='FactUrlaube',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('datum', models.DateField()),
                ('beschreibung', models.CharField(max_length=500)),
                ('gesamt_ausgaben', models.DecimalField(decimal_places=2, max_digits=18)),
                ('anteil_robert', models.DecimalField(decimal_places=2, max_digits=18)),
                ('anteil_sigi', models.DecimalField(decimal_places=2, max_digits=18)),
            ],
            options={
                'db_table': 'fact_urlaube',
                'managed': False,
                'ordering': ['-datum'],
                'verbose_name': 'Urlaub',
                'verbose_name_plural': 'Urlaube',
            },
        ),
    ]