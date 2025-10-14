# finance/management/commands/remap_produktgruppen.py
from django.core.management.base import BaseCommand
from finance.models import BillaProdukt


class Command(BaseCommand):
    help = 'Ordnet alle Produkte neu zu Produktgruppen und Überkategorien zu'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Zeigt nur an, was geändert würde, ohne zu speichern'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Überschreibt auch bereits zugeordnete Produkte'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']

        # === PRODUKTGRUPPEN-MAPPING ===
        # Die gleiche Struktur wie in produktgruppen_mapper.html
        produktgruppen_mapping = {
            # == == == == == GEMÜSE == == == == ==
            'Gemüse': {
                'Paprika': ['paprika', 'spitzpaprika'],
                'Tomaten': ['tomat', 'paradeiser', 'cherry', 'rispenparadeiser', 'markttomaten', 'rispenpara'],
                'Gurken': ['gurke', 'gurk'],
                'Salat': ['salat', 'rucola', 'eisberg', 'lollo', 'vogerlsalat', 'krauthäuptel'],
                'Zwiebeln': ['zwiebel', 'schalott', 'zwieb'],
                'Kartoffeln': ['kartoffel', 'erdäpfel', 'erdapfel', 'süßkartoffel', 'heurige'],
                'Karotten': ['karott', 'möhre', 'wurzel'],
                'Knoblauch': ['knoblauch'],
                'Kräuter': ['petersilie', 'schnittlauch', 'basilikum', 'koriander', 'dill', 'thymian', 'rosmarin', 'salbei',
                'kerbel', 'lorbeerbl', '8 kräutermix'],
                'Radieschen': ['radieschen'],
                'Zucchini': ['zucchini'],
                'Auberginen': ['aubergine', 'melanzani'],
                'Brokkoli': ['brokkoli', 'brocoli'],
                'Blumenkohl': ['blumenkohl', 'karfiol'],
                'Mais': ['mais', 'zuckermais'],
                'Erbsen': ['erbse', 'kichererbse'],
                'Bohnen': ['bohne', 'bohn', 'sojabohne', 'kidneybohne', 'riesenbohne', 'fisolen', 'edamame'],
                'Spinat': ['spinat', 'jungspinat', 'blattspinat'],
                'Lauch': ['lauch', 'porree'],
                'Kürbis': ['kürbis', 'hokkaido', 'butternuss'],
                'Ingwer': ['ingwer'],
                'Chili': ['chili', 'chiliwurzerl', 'peperoni'],
                'Spargel': ['spargel'],
                'Rüben': ['rübe', 'rote rübe', 'rote bete'],
                'Fenchel': ['fenchel'],
                'Kohl': ['kohl', 'kohlrabi', 'weißkohl', 'rotkohl', 'blumenkohl', 'rosenkohl', 'grünkohl', 'chinakohl',
                'pak choi'],
                'Sellerie': ['sellerie', 'stangensellerie'],
                'Gemüse Allgemein': ['gemüse', 'suppengemüse'],
                'Sprossen': ['sprossen', 'sprossengarten', 'kresse'],
                'Linsen': ['linsen', 'berglinsen'],
                'Polenta': ['polenta'],
            },

            # == == == == == OBST == == == == ==
            'Obst': {
                'Äpfel': ['apfel', 'äpfel'],
                'Bananen': ['banane'],
                'Orangen': ['orange', 'apfelsine'],
                'Zitronen': ['zitrone', 'limette', 'lime'],
                'Beeren': ['erdbeere', 'himbeere', 'heidelbeere', 'brombeere', 'beere', 'blaubeere'],
                'Trauben': ['traube', 'weintraube'],
                'Birnen': ['birne'],
                'Kiwi': ['kiwi'],
                'Mango': ['mango'],
                'Ananas': ['ananas'],
                'Pfirsich': ['pfirsich', 'nektarine'],
                'Melone': ['melone', 'wassermelone', 'honigmelone'],
                'Avocado': ['avocado'],
                'Granatapfel': ['granatapfel'],
                'Zwetschken': ['zwetschke', 'zwetsch', 'pflaume'],
                'Pomelo': ['pomelo'],
            },

            # == == == == == MILCHPRODUKTE == == == == ==
            'Milchprodukte': {
                'Milch': ['milch', 'h-milch', 'vollmilch', 'frischmilch'],
                'Joghurt': ['joghurt', 'jogurt', 'naturjoghurt', 'fruchtjoghu', 'billa bio fairtrade kokos'],
                'Käse': ['traungold', 'alpenprinz', 'käse', 'baron', 'schlossdamer', 'brie', 'jerome', 'moosbacher', 'schärd.', 'dachsteiner',
                'halloumi', 'baronesse', 'gouda', 'emmentaler', 'mozzarella', 'burrata', 'cheddar', 'camembert',
                'feta', 'ziegen', 'schafkäse', 'almkäse', 'bergkäse', 'edamer', 'tilsiter', 'parm.', 'regg.',
                'almkönig', 'goudette'],
                'Butter': ['butter', 'kräuterbutter', 'rama', 'lätta', 'margarine', 'viospread'],
                'Sahne': ['sahne', 'schlagobers', 'obers', 'creme fraiche', 'cremefine', 'kochcreme'],
                'Topfen': ['topfen', 'quark', 'magertopfen'],
                'Frischkäse': ['frischkäse', 'cottage'],
                'Mascarpone': ['mascarpone'],
                'Parmesan': ['parmesan', 'parmigiano', 'grana', 'padano'],
                'Ricotta': ['ricotta'],
                'Babybel': ['babybel'],
            },

            # == == == == == FLEISCH & WURST == == == == ==
            'Fleisch & Wurst': {
                'Rindfleisch': ['rindfleisch', 'rind ', 'steak', 'filetsteaks', 'tafelspitz', 'gulasch', 'grillmix'],
                'Schweinefleisch': ['schweinefleisch', 'schwein', 'karree'],
                'Hühnerfleisch': ['huhn', 'hähnchen', 'hühner', 'poulet', 'chicken', 'hendl', 'h-filet', 'geflügel',
                'unterkeulen'],
                'Putenfleisch': ['puten', 'pute'],
                'Wurst': ['wurst', 'würstel', 'würstchen', 'salami', 'leberkäse', 'knacker', 'debreziner', 'frankfurter',
                'kabanossi', 'griller', 'kaminwurzerl'],
                'Schinken': ['schinken', 'speck', 'bratl', 'bratenaufschnitt'],
                'Faschiertes': ['faschiert', 'hackfleisch', 'burger', 'beefburger'],
                'Würstchen': ['neuburger', 'braunschweiger', 'chorizo', 'salsiccia', 'cevapcici'],

            },

            # == == == == == FISCH == == == == ==
            'Fisch': {
                'Lachs': ['lachs'],
                'Thunfisch': ['thunfisch'],
                'Forelle': ['forelle'],
                'Garnelen': ['garnele', 'shrimp', 'crevette'],
                'Fisch': ['fisch', 'scholle'],
                'Makrelen': ['makrel'],
            },

            # == == == == == BROT & BACKWAREN == == == == ==
            'Brot & Backwaren': {
                'Brot': ['brot', 'bauernbrot', 'vollkornbrot', 'weißbrot', 'schwarzbrot', 'landbrot', 'krustenbrot',
                'baguette', 'ciabatta', 'fladenbrot', 'dinkel sandwich', 'sonntagsb'],
                'Semmeln': ['semmel', 'brötchen', 'weckerl', 'wecken', 'dachsteinweckerl'],
                'Toast': ['toast', 'toastbrot', 'mehrkorntoast', 'wasa'],
                'Gebäck': ['gebäck', 'croissant', 'plunder', 'krapfen', 'nougattasche', 'clever kräuter bag'],
                'Knäckebrot': ['knäcke', 'leicht cross', 'leicht & cross'],
                'Blätterteig': ['blätterteig'],
            },

            # == == == == == NUDELN & REIS == == == == ==
            'Nudeln & Reis': {
                'Nudeln': ['nudel', 'pasta', 'spaghetti', 'penne', 'fusilli', 'tagliatelle', 'rigatoni', 'farfalle',
                'tortellini', 'ravioli', 'parpadelle', 'fleckerl', 'bucati', 'girandole', 'lasagne'],
                'Gnocchi': ['gnocchi', 'schupfnudeln'],
                'Tortelloni': ['tortelloni'],
                'Reis': ['reis', 'basmati', 'risotto', 'reisfleisch'],
                'Quinoa': ['quinoa'],
                'Couscous': ['couscous'],
            },

            # == == == == == BACKEN == == == == ==
            'Backen': {
                'Mehl': ['mehl'],
                'Backpulver': ['backpulver'],
                'Hefe': ['hefe', 'backhefe', 'germ', 'keimkraft'],
                'Vanille': ['vanille', 'bourbon'],
                'Pudding': ['pudding'],
                'Gelatine': ['blattgelat'],
                'Panier': ['panko', 'panier', 'crumbs'],
            },

            # == == == == == SÜSSES == == == == ==
            'Süßes': {
                'Zucker': ['zucker', 'puderzucker', 'normalkristallz'],
                'Honig': ['honig'],
            },

            # == == == == == GEWÜRZE & WÜRZMITTEL == == == == ==
            'Gewürze & Würzmittel': {
                'Salz': ['salz'],
                'Pfeffer': ['pfeffer', 'cayennepf'],
                'Gewürze': ['gewürz', 'curry', 'paprikapulver', 'muskat', 'kümmel', 'zimt', 'sternanis', 'anis', 'nelke',
                'senf', 'koriander', 'kotanyi'],

            },

            # == == == == == ÖLE & ESSIG == == == == ==
            'Öle & Essig': {
                'Olivenöl': ['olivenöl'],
                'Sonnenblumenöl': ['sonnenblumenöl'],
                'Kürbisöl': ['kürbisöl'],
                'Essig': ['essig', 'balsamico'],
                'Natron': ['natron'],
                'Kokosöl': ['kokosöl'],
            },

            # == == == == == SOSSEN & AUFSTRICHE == == == == ==
            'Soßen & Aufstriche': {
                'Ketchup': ['ketchup'],
                'Mayonnaise': ['mayonnaise', 'mayo'],
                'Soßen': ['soße', 'sauce', 'hollandaise', 'pizzasauce'],
                'Dips': ['dip', 'tahin', 'sesam'],
                'Fond': ['fond'],
                'Letscho': ['letscho'],
                'Kren': ['kren', 'meerrettich'],
            },

            # == == == == == FRÜHSTÜCK == == == == ==
            'Frühstück': {
                'Müsli': ['müsli', 'knusperli', 'knusper pur', 'oetker knusper'],
                'Cornflakes': ['cornflakes', 'color loops'],
                'Haferflocken': ['haferflocken', 'hafer'],
                'Kaffee': ['kaffee', 'nescafé', 'nescafe', 'crema intenso', 'hornig'],
                'Porridge': ['porridge'],
            },

            # == == == == == SÜSSIGKEITEN & SNACKS == == == == ==
            'Süßigkeiten & Snacks': {
                'Schokolade': ['schokolade', 'schoko', 'nutella', 'kinder-pingui', 'manner'],
                'Kekse': ['keks', 'biskuit', 'cookie', 'biskotten', 'leibniz', 'pick up'],
                'Chips': ['chips', 'snips', 'best foodies bio bunte'],
                'Nüsse': ['nuss', 'mandel', 'walnüsse', 'haselnuss', 'walnuss', 'cashew', 'pistazie', 'erdnuss', 'studentenfutter',
                'studentenfutt', 'pinienkerne', 'sonnenblumenkerne', 'chiasamen'],
                'Trockenfrüchte': ['rosine', 'dattel', 'maroni'],
                'Süßigkeiten': ['tiramisu', 'duplo', 'suchard', 'celebrations', 'corny', 'trüffeltortenstück', 'sorger schwarzwälder'],
                'Proteinriegel': ['proteinriegel', 'barebells', 'neoh'],
                'Mohn': ['mohn'],

            },

            # == == == == == GETRÄNKE == == == == ==
            'Getränke': {
                'Wasser': ['wasser', 'mineralwasser', 'sicheldorfer', 'vöslauer'],
                'Saft': ['saft', 'nektar', 'rübensaft', 'fruchtik', 'innocent'],
                'Limonade': ['cola', 'sprite', 'fanta', 'limo'],
                'Bier': ['bier', 'radler', 'puntigamer'],
                'Wein': ['wein', 'rotwein', 'weißwein', 'weisswein', 'kremser', 'veltl', 'sandgrube', 'sauvignon',
                'les fumees', 'drautaler'],
                'Energy Drinks': ['red bull', 'energy'],
                'Hafermilch': ['hafermilch', 'haferdrink', 'oatly', 'barista', 'natrue coco'],
                'Sojamilch': ['sojamilch', 'sojadrink'],
                'Tee': ['tee', 'halsfreund', 'kamille', 'immun bio'],
                'Milchdrinks': ['lattella', 'nöm mix'],
                'Vegane Milch': ['vegavita no muuh'],
            },

            # == == == == == HYGIENE & KOSMETIK == == == == ==
            'Hygiene & Kosmetik': {
                'Shampoo': ['shampoo'],
                'Duschgel': ['duschgel', 'dusche'],
                'Deo': ['deo'],
                'Lippenpflege': ['lippenpflege'],
                'Zahnpflege': ['zahncreme', 'zahnspül', 'zahnpasta', 'colgate', 'blend-a-med', 'elmex', 'sensodyne',
                'corega'],
                'Wattestäbchen': ['wattestäbch', 'wattepads'],
                'Haargummis': ['haargummi', 'zopfhalter'],
                'Seife': ['seife', 'cremeseife'],
                'Desinfektionsmittel': ['desinfektions', 'dettol', 'lysoform'],
                'Haarspray': ['haarspray', 'taft'],
                'Sonnenschutz': ['sonnenspray', 'sonnenschutz', 'apres spray', 'nivea'],
                'Gel Pads': ['gel pads'],
                'Wachsstreifen': ['kaltwachs', 'veet'],
                'Waschgel': ['waschgel', 'gänseb'],
            },

            # == == == == == HAUSHALT & REINIGUNG == == == == ==
            'Haushalt & Reinigung': {
                'Reiniger': ['reiniger', 'frosch', 'dr. beckmann', 'rorax', 'clean&clear', 'bihome', 'lysofrom'],
                'Spülmittel': ['spülmittel'],
                'Toilettenpapier': ['toilettenpapier', 'klopapier'],
                'Küchenrolle': ['küchenrolle', 'kitchen towel'],
                'Backpapier': ['backpapier'],
                'Alufolie': ['alufolie', 'aluminiumfolie'],
                'Gefrierbeutel': ['gefrierbeutel', 'frischhaltebeutel', 'knotenbeutel'],
                'Müllbeutel': ['müllbeutel', 'mülltüte', 'swirl active frische', 'swirl aktive frische'],
                'Taschentücher': ['taschentuch', 'papiertaschentuch', 'tempo', 'feh taschentücher'],
                'Frischhaltefolie': ['toppits', 'frischhalte', 'swiffer'],
                'Weichspüler': ['silan'],
                'Brillenreiniger': ['brillenputz', 'brillenputztücher'],
                'Ohrstöpsel': ['ohropax'],
                'Waschmittel': ['persil', 'ariel', 'pulver', 'megapearls', 'dr. beck.gardinen'],
                'Entkalker': ['durgol', 'calgon'],
                'Geschirrspüler': ['finish', 'somat', 'klarspüler'],
                'WC-Reiniger': ['wc ente', 'wc power'],
                'Spülschwamm': ['spülschwamm', 'vileda'],
                'Reinigungstücher': ['reinigungstücher', 'bi care'],
                'Feuchttücher': ['feucht', 'topa'],
                'Wundspray': ['wund reinigungsspr'],
            },

            # == == == == == TIEFKÜHL == == == == ==
            'Tiefkühl': {
                'Tiefkühlkost': ['iglo', 'tk ', 'tiefkühl'],
                'Pizza': ['pizza', 'pizzamehl'],
                'Eis': ['eis ', 'cornetto', 'langnese', 'magnum', 'eskimo', 'cremissimo', 'mälzer&fu'],
                'Tortillas': ['tortilla', 'wrap', 'tex mex', 'corn&wheat'],
            },

            # == == == == == FERTIGGERICHTE == == == == ==
            'Fertiggerichte': {
                'Fertiggerichte': ['frisch gekocht', 'ready to eat'],
                'Suppen': ['suppe', 'rindsuppe'],
                'Cornichons': ['cornichons'],
            },

            # == == == == == TEXTILIEN & NON - FOOD == == == == ==
            'Textilien & Non-Food': {
                'Textilien': ['thermohose', 'mütze', 'kissen'],
                'Blumen & Pflanzen': ['palmkätzchen', 'blühplfanzen', 'adventkranz', 'markttulpen', 'blumen'],
                'Batterien': ['batterien', 'batter', 'varta'],
                'Geschenke & Deko': ['bon ', 'geschenk', 'neujahrsguß', 'happy birthay'],
                'Lichterketten': ['lichterkette', 'lichter', 'magnet-lichter'],
                'Diverses': ['non food', 'abverkauf', 'aktion', 'mailing', 'limited edition', 'bonus'],
            },

            # == == == == == SONSTIGES == == == == ==
            'Sonstiges': {
                'Pfandartikel': ['pfand', 'einwegpfand', 'pfandartikel', 'leergut', 'leergut-ret', 'leerflasche'],
                'Tragetaschen': ['tragetasche'],
                'Sonstiges': ['sonstiges', 'billa bon', 'äpp-only', 'unsere besten 6er', '8 x nimm mehr', 'stifterl',
                'schütt-streubehälter', 'tatü box', 'koro', 'bi good', 'gärtnerbund', 'lieblingsprodukt',
                'bio gourmet', 'landfr'],
            },
        }

        # Funktion zum Finden der Produktgruppe und Überkategorie
        def find_matching_group(produkt_name):
            if not produkt_name:
                return None, None

            name_lower = produkt_name.lower()

            for ueberkategorie, gruppen in produktgruppen_mapping.items():
                for produktgruppe, keywords in gruppen.items():
                    for keyword in keywords:
                        if keyword in name_lower:
                            return ueberkategorie, produktgruppe

            return None, None

        # === HAUPTLOGIK ===
        self.stdout.write('=' * 80)
        self.stdout.write(self.style.SUCCESS('🔄 PRODUKTGRUPPEN NEU ZUORDNEN'))
        self.stdout.write('=' * 80)

        if dry_run:
            self.stdout.write(self.style.WARNING('\n🔍 DRY RUN MODUS - Keine Änderungen werden gespeichert\n'))

        if force:
            produkte = BillaProdukt.objects.all()
            self.stdout.write(f'🔧 FORCE MODUS - Alle {produkte.count()} Produkte werden neu zugeordnet\n')
        else:
            produkte = BillaProdukt.objects.filter(
                ueberkategorie__isnull=True
            ) | BillaProdukt.objects.filter(
                produktgruppe__isnull=True
            )
            self.stdout.write(f'📦 Verarbeite {produkte.count()} Produkte ohne Zuordnung\n')

        stats = {
            'gesamt': 0,
            'aktualisiert': 0,
            'bereits_zugeordnet': 0,
            'nicht_gefunden': 0
        }

        nicht_gefunden_liste = []

        for produkt in produkte:
            stats['gesamt'] += 1

            # Finde passende Gruppe
            ueberkategorie, produktgruppe = find_matching_group(produkt.name_normalisiert)

            if ueberkategorie and produktgruppe:
                # Prüfe ob bereits zugeordnet und nicht force
                if not force and produkt.ueberkategorie and produkt.produktgruppe:
                    stats['bereits_zugeordnet'] += 1
                    continue

                if not dry_run:
                    produkt.ueberkategorie = ueberkategorie
                    produkt.produktgruppe = produktgruppe
                    produkt.save(update_fields=['ueberkategorie', 'produktgruppe'])

                stats['aktualisiert'] += 1

                # Ausgabe nur bei Änderungen
                if stats['aktualisiert'] % 10 == 0:
                    self.stdout.write(
                        f'✅ {stats["aktualisiert"]:4d} | {produkt.name_normalisiert[:40]:40s} → {ueberkategorie}'
                    )
            else:
                stats['nicht_gefunden'] += 1
                nicht_gefunden_liste.append(produkt.name_normalisiert)

        # === ABSCHLUSS ===
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(self.style.SUCCESS('📊 ZUSAMMENFASSUNG'))
        self.stdout.write('=' * 80)
        self.stdout.write(f'\n📦 Verarbeitet: {stats["gesamt"]} Produkte')

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'🔍 WÜRDEN aktualisiert: {stats["aktualisiert"]} Produkte'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Aktualisiert: {stats["aktualisiert"]} Produkte'
                )
            )

        if stats['bereits_zugeordnet'] > 0:
            self.stdout.write(f'⏭️  Übersprungen (bereits zugeordnet): {stats["bereits_zugeordnet"]}')

        if stats['nicht_gefunden'] > 0:
            self.stdout.write(
                self.style.WARNING(
                    f'❌ Nicht gefunden: {stats["nicht_gefunden"]} Produkte'
                )
            )

            self.stdout.write('\n📋 Erste 10 nicht zugeordnete Produkte:')
            for name in nicht_gefunden_liste[:10]:
                self.stdout.write(f'   - {name}')

        if dry_run:
            self.stdout.write(
                '\n' + self.style.WARNING(
                    '💡 Führe den Command ohne --dry-run aus zum Speichern:'
                )
            )
            self.stdout.write('   python manage.py remap_produktgruppen')

        if not force and stats['bereits_zugeordnet'] > 0:
            self.stdout.write(
                '\n' + self.style.WARNING(
                    '💡 Um ALLE Produkte neu zuzuordnen (auch bereits zugeordnete):'
                )
            )
            self.stdout.write('   python manage.py remap_produktgruppen --force')

        self.stdout.write('=' * 80)