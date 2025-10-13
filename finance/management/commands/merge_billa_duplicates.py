# finance/management/commands/merge_billa_duplicates.py
"""
Management Command zum Zusammenführen doppelter Billa-Produkte
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from finance.models import BillaProdukt, BillaArtikel, BillaPreisHistorie


class Command(BaseCommand):
    help = 'Führt doppelte Billa-Produkte zusammen (basierend auf normalisiertem Namen)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Zeigt nur an, was gemacht würde, ohne Änderungen durchzuführen',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('🔄 ZUSAMMENFÜHREN VON DUPLIKAT-PRODUKTEN'))
        self.stdout.write('=' * 70)

        if dry_run:
            self.stdout.write(self.style.WARNING('⚠️  DRY RUN MODUS - Keine Änderungen werden durchgeführt'))

        # Finde alle normalisierten Namen mit mehreren Einträgen
        duplicates = (
            BillaProdukt.objects.values('name_normalisiert')
            .annotate(count=Count('id'))
            .filter(count__gt=1)
            .order_by('-count')
        )

        total_duplicates = duplicates.count()
        self.stdout.write(f'\n📊 Gefundene Duplikate: {total_duplicates} normalisierte Namen\n')

        if total_duplicates == 0:
            self.stdout.write(self.style.SUCCESS('✅ Keine Duplikate gefunden!'))
            return

        merged_count = 0
        deleted_count = 0

        for dup in duplicates:
            name_norm = dup['name_normalisiert']
            produkte = list(BillaProdukt.objects.filter(name_normalisiert=name_norm).order_by('-anzahl_kaeufe', 'id'))

            # Das Produkt mit den meisten Käufen wird behalten
            master = produkte[0]
            duplicates_to_merge = produkte[1:]

            self.stdout.write(f'\n📦 {name_norm}')
            self.stdout.write(
                f'   Master: ID={master.id}, Käufe={master.anzahl_kaeufe}, Original="{master.name_original}"')

            for dupe in duplicates_to_merge:
                self.stdout.write(
                    f'   → Merge: ID={dupe.id}, Käufe={dupe.anzahl_kaeufe}, Original="{dupe.name_original}"')

            if not dry_run:
                with transaction.atomic():
                    # Verschiebe alle Artikel zum Master-Produkt
                    artikel_count = BillaArtikel.objects.filter(produkt__in=duplicates_to_merge).update(produkt=master)

                    # Verschiebe alle Preishistorie-Einträge
                    preis_count = BillaPreisHistorie.objects.filter(produkt__in=duplicates_to_merge).update(
                        produkt=master)

                    # Lösche die Duplikate
                    for dupe in duplicates_to_merge:
                        dupe.delete()
                        deleted_count += 1

                    # Aktualisiere Master-Statistiken
                    master.update_statistiken()

                    self.stdout.write(
                        self.style.SUCCESS(
                            f'   ✅ {artikel_count} Artikel und {preis_count} Preishistorie-Einträge verschoben'
                        )
                    )

            merged_count += 1

        self.stdout.write('\n' + '=' * 70)
        if dry_run:
            self.stdout.write(self.style.WARNING(f'🔍 WÜRDE {merged_count} Produkt-Gruppen zusammenführen'))
            self.stdout.write(self.style.WARNING(f'🔍 WÜRDE {deleted_count} Duplikate löschen'))
            self.stdout.write('\n💡 Führe den Command ohne --dry-run aus, um die Änderungen durchzuführen')
        else:
            self.stdout.write(self.style.SUCCESS(f'✅ {merged_count} Produkt-Gruppen zusammengeführt'))
            self.stdout.write(self.style.SUCCESS(f'✅ {deleted_count} Duplikate gelöscht'))
        self.stdout.write('=' * 70)