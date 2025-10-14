# finance/management/commands/analyze_billa.py

from django.core.management.base import BaseCommand
from django.db.models import Sum, Avg, Count, Max, Min
from finance.models import BillaEinkauf, BillaArtikel, BillaProdukt
from decimal import Decimal


class Command(BaseCommand):
    help = 'Zeigt Analysen der Billa-Einkäufe'

    def add_arguments(self, parser):
        parser.add_argument(
            'befehl',
            type=str,
            choices=['overview', 'top', 'preis', 'kategorien', 'filialen', 'export'],
            help='Art der Analyse'
        )
        parser.add_argument(
            '--produkt',
            type=str,
            help='Produktname für Preisanalyse'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=20,
            help='Anzahl Ergebnisse'
        )

    def handle(self, *args, **options):
        befehl = options['befehl']

        if befehl == 'overview':
            self.show_overview()
        elif befehl == 'top':
            self.show_top_products(options['limit'])
        elif befehl == 'preis':
            self.show_price_changes(options.get('produkt'), options['limit'])
        elif befehl == 'kategorien':
            self.show_categories()
        elif befehl == 'filialen':
            self.show_filialen()
        elif befehl == 'export':
            self.export_data()

    def show_overview(self):
        """Zeigt Gesamt-Übersicht"""
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('📊 BILLA ÜBERSICHT'))
        self.stdout.write('=' * 70)

        stats = BillaEinkauf.objects.aggregate(
            anzahl=Count('id'),
            gesamt=Sum('gesamt_preis'),
            ersparnis=Sum('gesamt_ersparnis'),
            avg_warenkorb=Avg('gesamt_preis')
        )

        self.stdout.write(f"\n📦 Anzahl Einkäufe: {stats['anzahl']}")
        self.stdout.write(f"💰 Gesamtausgaben: € {stats['gesamt']:,.2f}")
        self.stdout.write(f"💸 Gesamte Ersparnis: € {stats['ersparnis']:,.2f}")
        self.stdout.write(f"🛒 Ø Warenkorbwert: € {stats['avg_warenkorb']:,.2f}")

        if stats['gesamt']:
            ersparnis_pct = (stats['ersparnis'] / stats['gesamt'] * 100)
            self.stdout.write(f"📈 Ersparnis-Quote: {ersparnis_pct:.1f}%")

        # Zeitraum
        erste = BillaEinkauf.objects.earliest('datum')
        letzte = BillaEinkauf.objects.latest('datum')
        self.stdout.write(f"\n📅 Zeitraum: {erste.datum} bis {letzte.datum}")

        # Anzahl Artikel
        artikel_count = BillaArtikel.objects.count()
        produkte_count = BillaProdukt.objects.count()
        self.stdout.write(f"📦 Anzahl Artikel gesamt: {artikel_count:,}")
        self.stdout.write(f"🏷️  Anzahl verschiedene Produkte: {produkte_count:,}")

        if stats['anzahl']:
            avg_artikel = artikel_count / stats['anzahl']
            self.stdout.write(f"📊 Ø Artikel pro Einkauf: {avg_artikel:.1f}")

        self.stdout.write('=' * 70 + '\n')

    def show_top_products(self, limit):
        """Zeigt Top-Produkte"""
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS(f'🏆 TOP {limit} PRODUKTE'))
        self.stdout.write('=' * 70 + '\n')

        top = BillaArtikel.objects.values(
            'produkt__name_normalisiert',
            'produkt__ueberkategorie'  # ← GEÄNDERT von kategorie
        ).annotate(
            anzahl=Count('id'),
            ausgaben=Sum('gesamtpreis'),
            avg_preis=Avg('preis_pro_einheit')
        ).order_by('-anzahl')[:limit]

        for idx, item in enumerate(top, 1):
            ueberkategorie = item['produkt__ueberkategorie'] or 'Sonstiges'  # ← GEÄNDERT
            self.stdout.write(
                f"{idx:2d}. {item['produkt__name_normalisiert']:50s} "
                f"[{ueberkategorie}]"
            )
            self.stdout.write(
                f"    Anzahl: {item['anzahl']:3d} | "
                f"Gesamt: € {item['ausgaben']:7.2f} | "
                f"Ø Preis: € {item['avg_preis']:6.2f}\n"
            )

    def show_price_changes(self, produkt_name, limit):
        """Zeigt Preisänderungen"""
        if produkt_name:
            # Spezifisches Produkt
            try:
                produkt = BillaProdukt.objects.get(
                    name_normalisiert__icontains=produkt_name
                )
            except BillaProdukt.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"✗ Produkt nicht gefunden: {produkt_name}")
                )
                return
            except BillaProdukt.MultipleObjectsReturned:
                produkte = BillaProdukt.objects.filter(
                    name_normalisiert__icontains=produkt_name
                )
                self.stdout.write(
                    self.style.WARNING("⚠️  Mehrere Produkte gefunden:")
                )
                for p in produkte:
                    self.stdout.write(f"  - {p.name_normalisiert}")
                return

            self.stdout.write('=' * 70)
            self.stdout.write(
                self.style.SUCCESS(f'📈 PREISENTWICKLUNG: {produkt.name_normalisiert}')
            )
            self.stdout.write('=' * 70 + '\n')

            historie = produkt.preishistorie.order_by('datum')

            for h in historie:
                self.stdout.write(
                    f"{h.datum}: € {h.preis:6.2f} ({h.menge} {h.einheit}) - Filiale {h.filiale}"
                )

            if historie.count() > 1:
                preise = list(historie.values_list('preis', flat=True))
                min_preis = min(preise)
                max_preis = max(preise)
                diff = max_preis - min_preis
                diff_pct = (diff / min_preis * 100) if min_preis > 0 else 0

                self.stdout.write(f"\n📊 Min: € {min_preis:.2f} | Max: € {max_preis:.2f}")
                if diff > 0:
                    self.stdout.write(
                        self.style.WARNING(f"↑ Preisänderung: +€ {diff:.2f} (+{diff_pct:.1f}%)")
                    )
                elif diff < 0:
                    self.stdout.write(
                        self.style.SUCCESS(f"↓ Preisänderung: -€ {abs(diff):.2f} ({diff_pct:.1f}%)")
                    )

        else:
            # Alle Produkte mit Preisänderungen
            self.stdout.write('=' * 70)
            self.stdout.write(
                self.style.SUCCESS(f'📉 TOP {limit} PRODUKTE MIT GRÖßTEN PREISÄNDERUNGEN')
            )
            self.stdout.write('=' * 70 + '\n')

            produkte_mit_aenderung = []

            for produkt in BillaProdukt.objects.filter(anzahl_kaeufe__gte=3):
                preise = list(produkt.preishistorie.values_list('preis', flat=True))
                if len(preise) >= 2:
                    min_preis = min(preise)
                    max_preis = max(preise)
                    diff = max_preis - min_preis
                    diff_pct = (diff / min_preis * 100) if min_preis > 0 else 0

                    if diff > Decimal('0.5'):
                        produkte_mit_aenderung.append({
                            'produkt': produkt,
                            'min_preis': min_preis,
                            'max_preis': max_preis,
                            'diff': diff,
                            'diff_pct': diff_pct
                        })

            produkte_mit_aenderung.sort(key=lambda x: x['diff_pct'], reverse=True)

            for idx, item in enumerate(produkte_mit_aenderung[:limit], 1):
                self.stdout.write(
                    f"{idx:2d}. {item['produkt'].name_normalisiert:50s}"
                )
                self.stdout.write(
                    f"    Min: € {item['min_preis']:6.2f} | "
                    f"Max: € {item['max_preis']:6.2f} | "
                    f"Diff: +€ {item['diff']:6.2f} (+{item['diff_pct']:.1f}%)\n"
                )

    def show_categories(self):
        """Zeigt Ausgaben nach Überkategorien"""
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('🏷️  AUSGABEN NACH ÜBERKATEGORIE'))  # ← GEÄNDERT
        self.stdout.write('=' * 70 + '\n')

        kategorien = BillaArtikel.objects.values(
            'produkt__ueberkategorie'  # ← GEÄNDERT
        ).annotate(
            ausgaben=Sum('gesamtpreis'),
            anzahl=Count('id')
        ).order_by('-ausgaben')

        gesamt = sum(k['ausgaben'] for k in kategorien if k['ausgaben'])

        for item in kategorien:
            kat = item['produkt__ueberkategorie'] or 'Nicht zugeordnet'  # ← GEÄNDERT
            ausgaben = item['ausgaben'] or 0
            prozent = (ausgaben / gesamt * 100) if gesamt else 0

            self.stdout.write(
                f"{kat:25s}: € {ausgaben:8.2f} ({prozent:5.1f}%) "
                f"- {item['anzahl']:,} Artikel"
            )

        self.stdout.write(f"\n{'Gesamt':25s}: € {gesamt:8.2f}")
        self.stdout.write('=' * 70 + '\n')

    def show_filialen(self):
        """Zeigt Statistiken nach Filialen"""
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('🏪 AUSGABEN NACH FILIALE'))
        self.stdout.write('=' * 70 + '\n')

        filialen = BillaEinkauf.objects.values('filiale').annotate(
            anzahl=Count('id'),
            ausgaben=Sum('gesamt_preis'),
            ersparnis=Sum('gesamt_ersparnis'),
            avg_warenkorb=Avg('gesamt_preis')
        ).order_by('-ausgaben')

        for f in filialen:
            self.stdout.write(f"\n📍 Filiale {f['filiale']}")
            self.stdout.write(f"   Einkäufe: {f['anzahl']:3d}")
            self.stdout.write(f"   Ausgaben: € {f['ausgaben']:8.2f}")
            self.stdout.write(f"   Ersparnis: € {f['ersparnis']:7.2f}")
            self.stdout.write(f"   Ø Warenkorb: € {f['avg_warenkorb']:6.2f}")

        self.stdout.write('\n' + '=' * 70 + '\n')

    def export_data(self):
        """Exportiert Daten nach CSV"""
        import csv
        from datetime import datetime

        filename = f'billa_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Datum', 'Filiale', 'Produktname', 'Kategorie',
                'Menge', 'Einheit', 'Einzelpreis', 'Gesamtpreis',
                'Rabatt', 'Rabatt-Typ'
            ])

            for artikel in BillaArtikel.objects.select_related(
                    'einkauf', 'produkt'
            ).order_by('-einkauf__datum'):
                kategorie = artikel.produkt.get_kategorie_display() if artikel.produkt else ''

                writer.writerow([
                    artikel.einkauf.datum,
                    artikel.einkauf.filiale,
                    artikel.produkt_name,
                    kategorie,
                    artikel.menge,
                    artikel.einheit,
                    artikel.einzelpreis or '',
                    artikel.gesamtpreis,
                    artikel.rabatt,
                    artikel.rabatt_typ or ''
                ])

        self.stdout.write(
            self.style.SUCCESS(f'✓ Export erstellt: {filename}')
        )