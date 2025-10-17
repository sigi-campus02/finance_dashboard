from django.core.management.base import BaseCommand
from django.db import transaction
from billa.models import BillaProdukt, BillaUeberkategorie, BillaProduktgruppe
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Migriert bestehende Kategorien von CharField zu ForeignKey'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Starte Kategorie-Migration...'))

        # Zuerst alte CharField-Daten in temporäre Felder kopieren
        self.stdout.write('1. Sichere alte Daten...')
        with transaction.atomic():
            # Kopiere alte Werte in _alt Felder (falls noch nicht geschehen)
            BillaProdukt.objects.filter(
                ueberkategorie_alt__isnull=True
            ).update(
                ueberkategorie_alt=models.F('ueberkategorie')
            )

            BillaProdukt.objects.filter(
                produktgruppe_alt__isnull=True
            ).update(
                produktgruppe_alt=models.F('produktgruppe')
            )

        self.stdout.write(self.style.SUCCESS('✓ Alte Daten gesichert'))

        # Erstelle Überkategorien
        self.stdout.write('\n2. Erstelle Überkategorien...')
        ueberkategorien_map = self._create_ueberkategorien()
        self.stdout.write(self.style.SUCCESS(f'✓ {len(ueberkategorien_map)} Überkategorien erstellt'))

        # Erstelle Produktgruppen
        self.stdout.write('\n3. Erstelle Produktgruppen...')
        produktgruppen_map = self._create_produktgruppen(ueberkategorien_map)
        self.stdout.write(self.style.SUCCESS(f'✓ {len(produktgruppen_map)} Produktgruppen erstellt'))

        # Verknüpfe Produkte
        self.stdout.write('\n4. Verknüpfe Produkte mit neuen Kategorien...')
        updated = self._link_products(ueberkategorien_map, produktgruppen_map)
        self.stdout.write(self.style.SUCCESS(f'✓ {updated} Produkte verknüpft'))

        # Statistik
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('MIGRATION ABGESCHLOSSEN'))
        self.stdout.write('=' * 60)
        self._print_statistics()

    def _create_ueberkategorien(self):
        """Erstellt Überkategorien aus bestehenden Produkten"""

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

        ueberkategorien_map = {}

        # Hole alle eindeutigen Überkategorien aus den ALT-Feldern
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
                self.stdout.write(f'  + {kat_name}')

        return ueberkategorien_map

    def _create_produktgruppen(self, ueberkategorien_map):
        """Erstellt Produktgruppen aus bestehenden Produkten"""
        produktgruppen_map = {}

        # Hole alle eindeutigen Kombinationen aus ALT-Feldern
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

            # Hole Überkategorie-Objekt
            ueberkategorie_obj = ueberkategorien_map.get(ueberkat_name)

            if not ueberkategorie_obj:
                self.stdout.write(
                    self.style.WARNING(f'  ⚠ Überkategorie nicht gefunden: {ueberkat_name}')
                )
                continue

            obj, created = BillaProduktgruppe.objects.get_or_create(
                name=gruppe_name,
                ueberkategorie=ueberkategorie_obj
            )

            # Key für Map: "Überkategorie::Produktgruppe"
            key = f"{ueberkat_name}::{gruppe_name}"
            produktgruppen_map[key] = obj

            if created:
                self.stdout.write(f'  + {ueberkat_name} → {gruppe_name}')

        return produktgruppen_map

    def _link_products(self, ueberkategorien_map, produktgruppen_map):
        """Verknüpft Produkte mit den neuen Foreign Keys"""
        updated_count = 0

        produkte = BillaProdukt.objects.all()
        total = produkte.count()

        for idx, produkt in enumerate(produkte, 1):
            if idx % 100 == 0:
                self.stdout.write(f'  Fortschritt: {idx}/{total}')

            changed = False

            # Setze Überkategorie
            if produkt.ueberkategorie_alt:
                ueberkategorie_obj = ueberkategorien_map.get(produkt.ueberkategorie_alt)
                if ueberkategorie_obj and produkt.ueberkategorie != ueberkategorie_obj:
                    produkt.ueberkategorie = ueberkategorie_obj
                    changed = True

            # Setze Produktgruppe
            if produkt.ueberkategorie_alt and produkt.produktgruppe_alt:
                key = f"{produkt.ueberkategorie_alt}::{produkt.produktgruppe_alt}"
                produktgruppe_obj = produktgruppen_map.get(key)
                if produktgruppe_obj and produkt.produktgruppe != produktgruppe_obj:
                    produkt.produktgruppe = produktgruppe_obj
                    changed = True

            if changed:
                produkt.save(update_fields=['ueberkategorie', 'produktgruppe'])
                updated_count += 1

        return updated_count

    def _print_statistics(self):
        """Zeigt Statistiken nach der Migration"""
        total_produkte = BillaProdukt.objects.count()
        mit_ueberkategorie = BillaProdukt.objects.filter(
            ueberkategorie__isnull=False
        ).count()
        mit_produktgruppe = BillaProdukt.objects.filter(
            produktgruppe__isnull=False
        ).count()

        self.stdout.write(f'\nProdukte gesamt: {total_produkte}')
        self.stdout.write(f'Mit Überkategorie: {mit_ueberkategorie} ({mit_ueberkategorie / total_produkte * 100:.1f}%)')
        self.stdout.write(f'Mit Produktgruppe: {mit_produktgruppe} ({mit_produktgruppe / total_produkte * 100:.1f}%)')
        self.stdout.write(f'\nÜberkategorien: {BillaUeberkategorie.objects.count()}')
        self.stdout.write(f'Produktgruppen: {BillaProduktgruppe.objects.count()}')