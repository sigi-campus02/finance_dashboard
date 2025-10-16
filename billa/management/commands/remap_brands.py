# finance/management/commands/remap_brands.py
"""
Management Command zum Zuordnen von Marken zu Billa-Produkten
Analog zum remap_produktgruppen Command
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from billa.models import BillaProdukt
from billa.services.brand_mapper import BrandMapper


class Command(BaseCommand):
    help = 'Ordnet alle Produkte zu Marken zu (basierend auf Produktnamen)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Zeigt nur an, was geändert würde, ohne zu speichern'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Überschreibt auch bereits zugeordnete Marken'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']

        # === HEADER ===
        self.stdout.write('=' * 80)
        self.stdout.write(self.style.SUCCESS('🏷️  MARKEN NEU ZUORDNEN'))
        self.stdout.write('=' * 80)

        if dry_run:
            self.stdout.write(self.style.WARNING('\n🔍 DRY RUN MODUS - Keine Änderungen werden gespeichert\n'))

        # === PRODUKTE AUSWÄHLEN ===
        if force:
            produkte = BillaProdukt.objects.all()
            self.stdout.write(f'🔧 FORCE MODUS - Alle {produkte.count()} Produkte werden neu zugeordnet\n')
        else:
            produkte = BillaProdukt.objects.filter(
                Q(marke__isnull=True) | Q(marke='')
            )
            self.stdout.write(f'📦 {produkte.count()} Produkte ohne Marke werden verarbeitet\n')

        # === STATISTIKEN ===
        counter = {
            'gesamt': produkte.count(),
            'marke_gefunden': 0,
            'keine_marke': 0,
            'fehler': 0
        }

        marken_verteilung = {}

        # === HAUPTSCHLEIFE ===
        self.stdout.write('\n🔄 Verarbeite Produkte...\n')

        for i, produkt in enumerate(produkte, 1):
            try:
                # Marke extrahieren
                marke = BrandMapper.extract_brand(produkt.name_original)

                if marke:
                    counter['marke_gefunden'] += 1
                    marken_verteilung[marke] = marken_verteilung.get(marke, 0) + 1

                    # Speichern (wenn nicht dry-run)
                    if not dry_run:
                        produkt.marke = marke
                        produkt.save(update_fields=['marke'])

                    # Beispiel ausgeben (nur die ersten 5 pro Marke)
                    if marken_verteilung[marke] <= 5:
                        self.stdout.write(
                            f'  ✓ {produkt.name_original[:60]:<60} → {marke}'
                        )
                else:
                    counter['keine_marke'] += 1

                # Fortschritt alle 100 Produkte
                if i % 100 == 0:
                    self.stdout.write(f'  ... {i}/{counter["gesamt"]} verarbeitet')

            except Exception as e:
                counter['fehler'] += 1
                self.stdout.write(
                    self.style.ERROR(f'  ✗ Fehler bei {produkt.name_original}: {e}')
                )

        # === ABSCHLUSS-STATISTIKEN ===
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(self.style.SUCCESS('✅ FERTIG!'))
        self.stdout.write('=' * 80)

        self.stdout.write(f'\n📊 STATISTIKEN:')
        self.stdout.write(f'  Gesamt verarbeitet:  {counter["gesamt"]:>6}')
        self.stdout.write(f'  Marke gefunden:      {counter["marke_gefunden"]:>6}')
        self.stdout.write(f'  Keine Marke:         {counter["keine_marke"]:>6}')
        self.stdout.write(f'  Fehler:              {counter["fehler"]:>6}')

        erkennungsrate = (counter['marke_gefunden'] / counter['gesamt'] * 100) if counter['gesamt'] > 0 else 0
        self.stdout.write(f'\n  Erkennungsrate:      {erkennungsrate:.1f}%')

        # === MARKEN-VERTEILUNG ===
        if marken_verteilung:
            self.stdout.write('\n📋 MARKEN-VERTEILUNG (Top 20):')
            sortiert = sorted(marken_verteilung.items(), key=lambda x: x[1], reverse=True)[:20]
            for marke, anzahl in sortiert:
                self.stdout.write(f'  {marke:<25} {anzahl:>5} Produkte')

        if dry_run:
            self.stdout.write('\n' + self.style.WARNING('⚠️  DRY RUN - Keine Änderungen wurden gespeichert!'))
        else:
            self.stdout.write('\n' + self.style.SUCCESS('💾 Änderungen wurden in der Datenbank gespeichert.'))

        self.stdout.write('')