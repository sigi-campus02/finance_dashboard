from django.db import migrations


def migrate_categories_forward(apps, schema_editor):
    """Migriert Daten von CharField zu ForeignKey"""
    BillaProdukt = apps.get_model('billa', 'BillaProdukt')
    BillaUeberkategorie = apps.get_model('billa', 'BillaUeberkategorie')
    BillaProduktgruppe = apps.get_model('billa', 'BillaProduktgruppe')

    # Icon-Mapping
    KATEGORIE_ICONS = {
        'Gemüse': 'bi-basket',
        'Obst': 'bi-apple',
        'Milchprodukte': 'bi-cup-straw',
        'Fleisch & Wurst': 'bi-shop',
        'Fisch': 'bi-water',
        'Brot & Backwaren': 'bi-bread-slice',
        'Nudeln & Reis': 'bi-bowl',
        'Backen': 'bi-cake',
        'Süßes': 'bi-candy',
        'Gewürze & Würzmittel': 'bi-spice',
        'Öle & Essig': 'bi-droplet',
        'Soßen & Aufstriche': 'bi-jar',
        'Frühstück': 'bi-sunrise',
        'Süßigkeiten & Snacks': 'bi-bag',
        'Getränke': 'bi-cup',
        'Hygiene & Kosmetik': 'bi-droplet-half',
        'Haushalt & Reinigung': 'bi-house',
        'Tiefkühl': 'bi-snow',
        'Fertiggerichte': 'bi-box',
        'Textilien & Non-Food': 'bi-bag-fill',
        'Sonstiges': 'bi-three-dots'
    }

    print("\n" + "=" * 60)
    print("STARTE KATEGORIE-MIGRATION")
    print("=" * 60)

    # 1. Erstelle Überkategorien
    print("\n1. Erstelle Überkategorien...")
    ueberkategorien_map = {}

    alte_kategorien = BillaProdukt.objects.exclude(
        ueberkategorie_alt__isnull=True
    ).exclude(
        ueberkategorie_alt=''
    ).values_list('ueberkategorie_alt', flat=True).distinct()

    for kat_name in alte_kategorien:
        obj, created = BillaUeberkategorie.objects.get_or_create(
            name=kat_name,
            defaults={
                'icon': KATEGORIE_ICONS.get(kat_name, 'bi-box-seam')
            }
        )
        ueberkategorien_map[kat_name] = obj
        if created:
            print(f"  + {kat_name}")

    print(f"✓ {len(ueberkategorien_map)} Überkategorien erstellt")

    # 2. Erstelle Produktgruppen
    print("\n2. Erstelle Produktgruppen...")
    produktgruppen_map = {}

    kombinationen = BillaProdukt.objects.exclude(
        ueberkategorie_alt__isnull=True
    ).exclude(
        produktgruppe_alt__isnull=True
    ).exclude(
        ueberkategorie_alt=''
    ).exclude(
        produktgruppe_alt=''
    ).values('ueberkategorie_alt', 'produktgruppe_alt').distinct()

    for kombi in kombinationen:
        ueberkat_name = kombi['ueberkategorie_alt']
        gruppe_name = kombi['produktgruppe_alt']

        ueberkategorie_obj = ueberkategorien_map.get(ueberkat_name)
        if not ueberkategorie_obj:
            continue

        obj, created = BillaProduktgruppe.objects.get_or_create(
            name=gruppe_name,
            ueberkategorie=ueberkategorie_obj
        )

        key = f"{ueberkat_name}::{gruppe_name}"
        produktgruppen_map[key] = obj

        if created:
            print(f"  + {ueberkat_name} → {gruppe_name}")

    print(f"✓ {len(produktgruppen_map)} Produktgruppen erstellt")

    # 3. Verknüpfe Produkte
    print("\n3. Verknüpfe Produkte...")
    updated_count = 0

    produkte = BillaProdukt.objects.all()
    total = produkte.count()

    for idx, produkt in enumerate(produkte, 1):
        if idx % 500 == 0:
            print(f"  Fortschritt: {idx}/{total}")

        changed = False

        # Setze Überkategorie
        if produkt.ueberkategorie_alt:
            ueberkategorie_obj = ueberkategorien_map.get(produkt.ueberkategorie_alt)
            if ueberkategorie_obj:
                produkt.ueberkategorie = ueberkategorie_obj
                changed = True

        # Setze Produktgruppe
        if produkt.ueberkategorie_alt and produkt.produktgruppe_alt:
            key = f"{produkt.ueberkategorie_alt}::{produkt.produktgruppe_alt}"
            produktgruppe_obj = produktgruppen_map.get(key)
            if produktgruppe_obj:
                produkt.produktgruppe = produktgruppe_obj
                changed = True

        if changed:
            produkt.save(update_fields=['ueberkategorie', 'produktgruppe'])
            updated_count += 1

    print(f"✓ {updated_count} Produkte verknüpft")

    # Statistiken
    print("\n" + "=" * 60)
    print("MIGRATION ABGESCHLOSSEN")
    print("=" * 60)
    total_produkte = BillaProdukt.objects.count()
    mit_ueberkategorie = BillaProdukt.objects.filter(ueberkategorie__isnull=False).count()
    mit_produktgruppe = BillaProdukt.objects.filter(produktgruppe__isnull=False).count()

    print(f'\nProdukte gesamt: {total_produkte}')
    if total_produkte:
        print(f'Mit Überkategorie: {mit_ueberkategorie} ({mit_ueberkategorie / total_produkte * 100:.1f}%)')
        print(f'Mit Produktgruppe: {mit_produktgruppe} ({mit_produktgruppe / total_produkte * 100:.1f}%)')
    else:
        print('Mit Überkategorie: 0 (0.0%)')
        print('Mit Produktgruppe: 0 (0.0%)')
    print(f'\nÜberkategorien: {BillaUeberkategorie.objects.count()}')
    print(f'Produktgruppen: {BillaProduktgruppe.objects.count()}')
    print("")


def migrate_categories_backward(apps, schema_editor):
    """Rollback: Kopiere FK-Daten zurück zu CharField"""
    BillaProdukt = apps.get_model('billa', 'BillaProdukt')

    for produkt in BillaProdukt.objects.all():
        if produkt.ueberkategorie:
            produkt.ueberkategorie_alt = produkt.ueberkategorie.name
        if produkt.produktgruppe:
            produkt.produktgruppe_alt = produkt.produktgruppe.name
        produkt.save(update_fields=['ueberkategorie_alt', 'produktgruppe_alt'])


class Migration(migrations.Migration):
    dependencies = [
        ('billa', '0008_add_new_fk_fields'),
    ]

    operations = [
        migrations.RunPython(
            migrate_categories_forward,
            migrate_categories_backward
        ),
    ]