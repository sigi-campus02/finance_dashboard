# finance/management/commands/fix_missing_ueberkategorien.py
from django.core.management.base import BaseCommand
from django.db.models import Q
from billa.models import BillaProdukt


class Command(BaseCommand):
    help = 'Ordnet fehlende Überkategorien basierend auf Produktgruppen zu'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Zeigt nur an, was geändert würde, ohne zu speichern'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Mapping von Produktgruppe zu Überkategorie
        # Basierend auf der Struktur aus billa_produktgruppen_mapper.html
        produktgruppe_zu_ueberkategorie = {
            # Gemüse
            'Paprika': 'Gemüse',
            'Tomaten': 'Gemüse',
            'Gurken': 'Gemüse',
            'Salat': 'Gemüse',
            'Zwiebeln': 'Gemüse',
            'Kartoffeln': 'Gemüse',
            'Karotten': 'Gemüse',
            'Knoblauch': 'Gemüse',
            'Kräuter': 'Gemüse',
            'Radieschen': 'Gemüse',
            'Zucchini': 'Gemüse',
            'Auberginen': 'Gemüse',
            'Brokkoli': 'Gemüse',
            'Blumenkohl': 'Gemüse',
            'Mais': 'Gemüse',
            'Erbsen': 'Gemüse',
            'Bohnen': 'Gemüse',
            'Spinat': 'Gemüse',
            'Lauch': 'Gemüse',
            'Kürbis': 'Gemüse',
            'Ingwer': 'Gemüse',
            'Chili': 'Gemüse',
            'Spargel': 'Gemüse',
            'Rüben': 'Gemüse',
            'Fenchel': 'Gemüse',
            'Kohl': 'Gemüse',
            'Sellerie': 'Gemüse',
            'Sprossen': 'Gemüse',

            # Obst
            'Äpfel': 'Obst',
            'Bananen': 'Obst',
            'Beeren': 'Obst',
            'Zitrusfrüchte': 'Obst',
            'Trauben': 'Obst',
            'Birnen': 'Obst',
            'Kiwis': 'Obst',
            'Melonen': 'Obst',
            'Pfirsiche': 'Obst',
            'Pflaumen': 'Obst',
            'Ananas': 'Obst',
            'Mango': 'Obst',
            'Avocado': 'Obst',

            # Milchprodukte
            'Milch': 'Milchprodukte',
            'Joghurt': 'Milchprodukte',
            'Käse': 'Milchprodukte',
            'Butter': 'Milchprodukte',
            'Sahne': 'Milchprodukte',
            'Quark': 'Milchprodukte',
            'Frischkäse': 'Milchprodukte',
            'Eier': 'Milchprodukte',
            'Mascarpone': 'Milchprodukte',
            'Parmesan': 'Milchprodukte',

            # Fleisch & Wurst
            'Rind': 'Fleisch & Wurst',
            'Schwein': 'Fleisch & Wurst',
            'Geflügel': 'Fleisch & Wurst',
            'Wurst': 'Fleisch & Wurst',
            'Schinken': 'Fleisch & Wurst',
            'Faschiertes': 'Fleisch & Wurst',
            'Würstchen': 'Fleisch & Wurst',

            # Fisch
            'Lachs': 'Fisch',
            'Thunfisch': 'Fisch',
            'Forelle': 'Fisch',
            'Garnelen': 'Fisch',
            'Fisch': 'Fisch',
            'Makrelen': 'Fisch',

            # Brot & Backwaren
            'Brot': 'Brot & Backwaren',
            'Brötchen': 'Brot & Backwaren',
            'Gebäck': 'Brot & Backwaren',
            'Toast': 'Brot & Backwaren',

            # Getränke
            'Wasser': 'Getränke',
            'Saft': 'Getränke',
            'Limonade': 'Getränke',
            'Bier': 'Getränke',
            'Wein': 'Getränke',
            'Energy Drinks': 'Getränke',
            'Hafermilch': 'Getränke',
            'Sojamilch': 'Getränke',
            'Tee': 'Getränke',
            'Milchdrinks': 'Getränke',
            'Vegane Milch': 'Getränke',

            # Weitere Kategorien...
            'Nudeln': 'Nudeln & Reis',
            'Reis': 'Nudeln & Reis',
            'Gnocchi': 'Nudeln & Reis',
            'Couscous': 'Nudeln & Reis',
            'Quinoa': 'Nudeln & Reis',

            'Schokolade': 'Süßigkeiten & Snacks',
            'Kekse': 'Süßigkeiten & Snacks',
            'Chips': 'Süßigkeiten & Snacks',
            'Nüsse': 'Süßigkeiten & Snacks',

            'Tiefkühlkost': 'Tiefkühl',
            'Pizza': 'Tiefkühl',
            'Eis': 'Tiefkühl',

            'Shampoo': 'Hygiene & Kosmetik',
            'Duschgel': 'Hygiene & Kosmetik',
            'Deo': 'Hygiene & Kosmetik',
            'Zahnpflege': 'Hygiene & Kosmetik',

            'Reiniger': 'Haushalt & Reinigung',
            'Spülmittel': 'Haushalt & Reinigung',
            'Toilettenpapier': 'Haushalt & Reinigung',
            'Waschmittel': 'Haushalt & Reinigung',
        }

        # Produkte ohne Überkategorie oder mit "NULL" finden
        produkte = BillaProdukt.objects.filter(
            Q(ueberkategorie__isnull=True) | Q(ueberkategorie='NULL') | Q(ueberkategorie='')
        ).exclude(
            produktgruppe__isnull=True
        ).exclude(
            produktgruppe=''
        )

        self.stdout.write('=' * 80)
        self.stdout.write(self.style.SUCCESS('🔧 ÜBERKATEGORIEN ZUORDNEN'))
        self.stdout.write('=' * 80)

        total = produkte.count()
        self.stdout.write(f'\n📊 Gefunden: {total} Produkte ohne Überkategorie\n')

        if total == 0:
            self.stdout.write(self.style.SUCCESS('✅ Alle Produkte haben bereits eine Überkategorie!'))
            return

        updated = 0
        not_found = []

        for produkt in produkte:
            produktgruppe = produkt.produktgruppe
            ueberkategorie = produktgruppe_zu_ueberkategorie.get(produktgruppe)

            if ueberkategorie:
                if not dry_run:
                    produkt.ueberkategorie = ueberkategorie
                    produkt.save(update_fields=['ueberkategorie'])

                self.stdout.write(
                    f'✅ {produkt.name_normalisiert[:50]:50s} | '
                    f'{produktgruppe:20s} → {ueberkategorie}'
                )
                updated += 1
            else:
                not_found.append((produkt.name_normalisiert, produktgruppe))

        self.stdout.write('\n' + '=' * 80)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'\n🔍 DRY RUN: {updated} Produkte WÜRDEN aktualisiert werden'
                )
            )
            self.stdout.write('   Führe den Command ohne --dry-run aus zum Speichern.\n')
        else:
            self.stdout.write(
                self.style.SUCCESS(f'\n✅ {updated} Produkte aktualisiert!')
            )

        if not_found:
            self.stdout.write(
                self.style.WARNING(
                    f'\n⚠️  {len(not_found)} Produktgruppen ohne Mapping:'
                )
            )
            for name, gruppe in not_found[:20]:
                self.stdout.write(f'   - {gruppe}: {name[:50]}')

            self.stdout.write(
                '\n💡 Tipp: Füge diese Produktgruppen zum Mapping hinzu!'
            )

        self.stdout.write('=' * 80)