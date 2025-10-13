# finance/migrations/0004_fix_produkt_duplikate.py
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0003_billakategoriemapping_billaeinkauf_billaprodukt_and_more'),
    ]

    operations = [
        # 1. Entferne unique constraint von name_original
        migrations.AlterField(
            model_name='billaprodukt',
            name='name_original',
            field=models.CharField(max_length=500, verbose_name='Original-Name'),
        ),

        # 2. Füge unique constraint zu name_normalisiert hinzu
        migrations.AlterField(
            model_name='billaprodukt',
            name='name_normalisiert',
            field=models.CharField(max_length=500, db_index=True, unique=True, verbose_name='Normalisierter Name'),
        ),
    ]