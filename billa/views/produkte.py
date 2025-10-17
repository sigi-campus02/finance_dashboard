from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
import json
from django.db.models import Sum, Count, Q, Min, Max, Avg
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.views.decorators.http import require_POST
import logging
from billa.models import (
    BillaArtikel, BillaProdukt, BillaPreisHistorie
)

logger = logging.getLogger(__name__)


@login_required
def billa_produkt_detail(request, produkt_id):
    """
    Detail-Ansicht eines Produkts - zeigt ALLE Varianten mit gleichem name_korrigiert
    """
    import json
    from django.db.models import Min, Max, Avg, Count, Sum

    # Hole das ursprüngliche Produkt
    hauptprodukt = get_object_or_404(BillaProdukt, pk=produkt_id)

    # Hole ALLE Produkte mit dem gleichen name_korrigiert
    alle_varianten = BillaProdukt.objects.filter(
        name_korrigiert=hauptprodukt.name_korrigiert
    ).order_by('-anzahl_kaeufe')

    anzahl_varianten = alle_varianten.count()

    # ========================================================================
    # AGGREGIERTE STATISTIKEN über alle Varianten
    # ========================================================================

    # Alle Artikel von allen Varianten
    alle_artikel = BillaArtikel.objects.filter(
        produkt__name_korrigiert=hauptprodukt.name_korrigiert
    )

    stats_gesamt = alle_artikel.aggregate(
        anzahl_kaeufe=Count('id'),
        min_preis=Min('preis_pro_einheit'),
        max_preis=Max('preis_pro_einheit'),
        avg_preis=Avg('preis_pro_einheit'),
        gesamt_ausgaben=Sum('gesamtpreis')
    )

    # ========================================================================
    # PREISENTWICKLUNG über alle Varianten
    # ========================================================================

    # Kombinierte Preisentwicklung aller Varianten
    preis_historie_raw = BillaPreisHistorie.objects.filter(
        produkt__name_korrigiert=hauptprodukt.name_korrigiert
    ).order_by('datum')

    # JSON für Chart vorbereiten
    preis_historie_json = []
    for h in preis_historie_raw:
        preis_historie_json.append({
            'datum': h.datum.strftime('%Y-%m-%d'),
            'preis': float(h.preis),
            'menge': float(h.menge),
            'filiale': h.filiale.name if h.filiale else 'Unbekannt',
            'produkt_id': h.produkt.id  # Um Varianten zu unterscheiden
        })

    # ========================================================================
    # LETZTE KÄUFE über alle Varianten
    # ========================================================================

    letzte_kaeufe = alle_artikel.select_related(
        'einkauf', 'produkt'
    ).order_by('-einkauf__datum')[:30]

    # ========================================================================
    # STATISTIKEN PRO VARIANTE
    # ========================================================================

    varianten_stats = []
    for variante in alle_varianten:
        variante_artikel = variante.artikel.aggregate(
            anzahl=Count('id'),
            ausgaben=Sum('gesamtpreis'),
            avg_preis=Avg('preis_pro_einheit')
        )

        varianten_stats.append({
            'variante': variante,
            'anzahl_kaeufe': variante_artikel['anzahl'] or 0,
            'ausgaben': variante_artikel['ausgaben'] or 0,
            'avg_preis': variante_artikel['avg_preis']
        })

    # ========================================================================
    # FILIALEN-VERTEILUNG
    # ========================================================================

    filialen_stats = alle_artikel.values(
        'einkauf__filiale__name'
    ).annotate(
        anzahl=Count('id'),
        ausgaben=Sum('gesamtpreis')
    ).order_by('-anzahl')

    context = {
        'hauptprodukt': hauptprodukt,
        'alle_varianten': alle_varianten,
        'anzahl_varianten': anzahl_varianten,
        'stats_gesamt': stats_gesamt,
        'preis_historie': json.dumps(preis_historie_json),
        'letzte_kaeufe': letzte_kaeufe,
        'varianten_stats': varianten_stats,
        'filialen_stats': filialen_stats,
    }

    return render(request, 'billa/billa_produkt_detail.html', context)


@login_required
def billa_produkte_liste(request):
    """
    Liste aller Produkte - GRUPPIERT nach name_korrigiert
    """
    import json
    from django.db.models import Q, Count, Sum, Avg, Min

    # Filter
    ueberkategorie = request.GET.get('ueberkategorie')
    produktgruppe = request.GET.get('produktgruppe')
    suche = request.GET.get('suche')
    sortierung = request.GET.get('sort', '-anzahl_kaeufe')

    # ========================================================================
    # GRUPPIERUNG nach name_korrigiert
    # ========================================================================
    produkte_grouped = BillaProdukt.objects.values(
        'name_korrigiert',
        'ueberkategorie',
        'produktgruppe'
    ).annotate(
        anzahl_varianten=Count('id'),
        gesamt_kaeufe=Sum('anzahl_kaeufe'),
        durchschnittspreis=Avg('durchschnittspreis'),
        letzter_preis=Avg('letzter_preis'),
        erste_id=Min('id')  # Für Detail-Link
    )

    # Filter nach Überkategorie
    if ueberkategorie and ueberkategorie != 'alle':
        produkte_grouped = produkte_grouped.filter(ueberkategorie=ueberkategorie)

    # Filter nach Produktgruppe
    if produktgruppe and produktgruppe != 'alle':
        produkte_grouped = produkte_grouped.filter(produktgruppe=produktgruppe)

    # Suche
    if suche:
        produkte_grouped = produkte_grouped.filter(
            Q(name_korrigiert__icontains=suche)
        )

    # Sortierung
    sortierung_map = {
        '-anzahl_kaeufe': '-gesamt_kaeufe',
        'anzahl_kaeufe': 'gesamt_kaeufe',
        '-durchschnittspreis': '-durchschnittspreis',
        'durchschnittspreis': 'durchschnittspreis',
        'name_korrigiert': 'name_korrigiert',
        '-name_korrigiert': '-name_korrigiert'
    }
    produkte_grouped = produkte_grouped.order_by(
        sortierung_map.get(sortierung, '-gesamt_kaeufe')
    )

    # ========================================================================
    # Filter-Optionen
    # ========================================================================
    alle_ueberkategorien = BillaProdukt.objects.values_list(
        'ueberkategorie', flat=True
    ).distinct().exclude(
        ueberkategorie__isnull=True
    ).exclude(
        ueberkategorie=''
    ).order_by('ueberkategorie')

    alle_produktgruppen = BillaProdukt.objects.values_list(
        'produktgruppe', flat=True
    ).distinct().exclude(
        produktgruppe__isnull=True
    ).exclude(
        produktgruppe=''
    ).order_by('produktgruppe')

    # ========================================================================
    # Produktgruppen-Mapping für JavaScript
    # ========================================================================
    produktgruppen_by_ueberkategorie = {}
    for ukat in alle_ueberkategorien:
        gruppen = BillaProdukt.objects.filter(
            ueberkategorie=ukat
        ).values_list('produktgruppe', flat=True).distinct().exclude(
            produktgruppe__isnull=True
        ).exclude(
            produktgruppe=''
        ).order_by('produktgruppe')
        produktgruppen_by_ueberkategorie[ukat] = list(gruppen)

    context = {
        'produkte': produkte_grouped,
        'ueberkategorien': list(alle_ueberkategorien),
        'produktgruppen': list(alle_produktgruppen),
        'selected_ueberkategorie': ueberkategorie or 'alle',
        'selected_produktgruppe': produktgruppe or 'alle',
        'selected_kategorie_display': ueberkategorie or 'Alle Kategorien',
        'suche': suche or '',
        'sortierung': sortierung,
        'produktgruppen_by_ueberkategorie': json.dumps(produktgruppen_by_ueberkategorie)
    }

    return render(request, 'billa/billa_produkte_liste.html', context)


# ============================================================================
# NEUE View für Bulk Update
# ============================================================================

@login_required
@require_POST
def bulk_update_by_name(request):
    """
    Updated ALLE BillaProdukt Objekte mit gleichem name_korrigiert
    """
    try:
        data = json.loads(request.body)
        name_korrigiert = data.get('name_korrigiert')
        ueberkategorie = data.get('ueberkategorie')
        produktgruppe = data.get('produktgruppe')

        if not name_korrigiert:
            return JsonResponse({
                'status': 'error',
                'message': 'name_korrigiert fehlt'
            }, status=400)

        # Update alle Produkte mit diesem name_korrigiert
        update_dict = {
            'ueberkategorie': ueberkategorie if ueberkategorie else None,
            'produktgruppe': produktgruppe if produktgruppe else None
        }

        updated_count = BillaProdukt.objects.filter(
            name_korrigiert=name_korrigiert
        ).update(**update_dict)

        logger.info(f"Bulk update: {updated_count} Produkte mit name_korrigiert='{name_korrigiert}' aktualisiert")

        return JsonResponse({
            'status': 'success',
            'updated': updated_count,
            'message': f'{updated_count} Produkt(e) aktualisiert'
        })

    except Exception as e:
        logger.error(f"Fehler beim Bulk Update: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@login_required
def billa_produktgruppen_mapper(request):
    """Mapper für Produktgruppen mit manueller Zuordnung"""

    # Produktgruppen-Definitionen
    PRODUKTGRUPPEN_MAP = {
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
            'Erbsen': ['erbse', 'kichererbs'],
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
            'Pilze': ['pilze', 'champignon', 'eierschwammerl', 'schwammerl'],
        },
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
        'Milchprodukte': {
            'Milch': ['milch', 'h-milch', 'vollmilch', 'frischmilch'],
            'Joghurt': ['joghurt', 'jogurt', 'naturjoghurt', 'fruchtjoghu', 'billa bio fairtrade kokos'],
            'Käse': ['traungold', 'alpenprinz', 'käse', 'gruyere', 'baron', 'schlossdamer', 'brie', 'jerome',
                     'moosbacher', 'schärd.', 'dachsteiner', 'halloumi', 'baronesse', 'gouda', 'emmentaler',
                     'mozzarella', 'burrata', 'cheddar', 'camembert', 'feta', 'ziegen', 'schafkäse', 'almkäse',
                     'bergkäse', 'edamer', 'tilsiter', 'parm.', 'regg.', 'almkönig', 'goudette'],
            'Butter': ['butter', 'kräuterbutter', 'rama', 'lätta', 'margarine', 'viospread'],
            'Sahne': ['sahne', 'schlagobers', 'obers', 'creme fraiche', 'cremefine', 'kochcreme'],
            'Topfen': ['topfen', 'quark', 'magertopfen'],
            'Frischkäse': ['frischkäse', 'cottage'],
            'Mascarpone': ['mascarpone'],
            'Parmesan': ['parmesan', 'parmigiano', 'grana', 'padano'],
            'Ricotta': ['ricotta'],
            'Babybel': ['babybel'],
            'Eier': ['eier', 'ei ', 'freilandeier', 'fl-eier', 'bh-eier', 'bio eier'],
        },
        'Fleisch & Wurst': {
            'Rindfleisch': ['rindfleisch', 'rind ', 'steak', 'filetsteaks', 'tafelspitz', 'gulasch', 'grillmix'],
            'Schweinefleisch': ['schweinefleisch', 'schwein', 'karree'],
            'Hühnerfleisch': ['huhn', 'hähnchen', 'hühner', 'poulet', 'chicken', 'hendl', 'h-filet', 'geflügel',
                              'unterkeulen'],
            'Putenfleisch': ['puten', 'pute'],
            'Wurst': ['wurst', 'würstel', 'würstchen', 'salami', 'leberkäse', 'knacker', 'debreziner', 'frankfurter',
                      'kabanossi', 'griller', 'kaminwurzerl'],
            'Schinken': ['schinken', 'speck', 'bratl', 'bratenaufschnitt', 'prosciutto'],
            'Faschiertes': ['faschiert', 'hackfleisch', 'burger', 'beefburger'],
            'Würstchen': ['neuburger', 'braunschweiger', 'chorizo', 'salsiccia', 'cevapcici'],
        },
        'Fisch': {
            'Lachs': ['lachs'],
            'Thunfisch': ['thunfisch'],
            'Forelle': ['forelle'],
            'Garnelen': ['garnele', 'shrimp', 'crevette'],
            'Fisch': ['fisch', 'scholle'],
            'Makrelen': ['makrel'],
        },
        'Brot & Backwaren': {
            'Brot': ['brot', 'bauernbrot', 'vollkornbrot', 'weißbrot', 'schwarzbrot', 'landbrot', 'krustenbrot',
                     'baguette', 'ciabatta', 'fladenbrot', 'dinkel sandwich', 'sonntagsb'],
            'Semmeln': ['semmel', 'brötchen', 'weckerl', 'wecken', 'dachsteinweckerl'],
            'Toast': ['toast', 'toastbrot', 'mehrkorntoast', 'wasa'],
            'Gebäck': ['gebäck', 'croissant', 'plunder', 'krapfen', 'nougattasche', 'clever kräuter bag'],
            'Knäckebrot': ['knäcke', 'leicht cross', 'leicht & cross'],
            'Blätterteig': ['blätterteig'],
            'Tortillas': ['tortilla', 'wrap', 'tex mex', 'corn&wheat', 'fajita', 'tort.'],
        },
        'Nudeln & Reis': {
            'Nudeln': ['nudel', 'pasta', 'spaghetti', 'penne', 'fusilli', 'tagliatelle', 'rigatoni', 'farfalle',
                       'tortellini', 'ravioli', 'parpadelle', 'fleckerl', 'bucati', 'girandole', 'lasagne'],
            'Gnocchi': ['gnocchi', 'schupfnudeln'],
            'Tortelloni': ['tortelloni'],
            'Reis': ['reis', 'basmati', 'risotto', 'reisfleisch'],
            'Quinoa': ['quinoa'],
            'Couscous': ['couscous'],
        },
        'Backen': {
            'Mehl': ['mehl'],
            'Backpulver': ['backpulver'],
            'Hefe': ['hefe', 'backhefe', 'germ', 'keimkraft'],
            'Vanille': ['vanille', 'bourbon'],
            'Pudding': ['pudding'],
            'Gelatine': ['blattgelat'],
            'Panier': ['panko', 'panier', 'crumbs'],
        },
        'Süßes': {
            'Zucker': ['zucker', 'puderzucker', 'normalkristallz'],
            'Honig': ['honig'],
        },
        'Gewürze & Würzmittel': {
            'Salz': ['salz'],
            'Pfeffer': ['pfeffer', 'cayennepf'],
            'Gewürze': ['gewürz', 'curry', 'paprikapulver', 'muskat', 'kümmel', 'zimt', 'sternanis', 'anis', 'nelke',
                        'senf', 'koriander', 'kotanyi'],
        },
        'Öle & Essig': {
            'Olivenöl': ['olivenöl'],
            'Sonnenblumenöl': ['sonnenblumenöl'],
            'Kürbisöl': ['kürbisöl'],
            'Essig': ['essig', 'balsamico'],
            'Natron': ['natron'],
            'Kokosöl': ['kokosöl'],
        },
        'Soßen & Aufstriche': {
            'Ketchup': ['ketchup'],
            'Mayonnaise': ['mayonnaise', 'mayo'],
            'Soßen': ['soße', 'sauce', 'hollandaise', 'pizzasauce'],
            'Dips': ['dip', 'tahin', 'sesam'],
            'Fond': ['fond'],
            'Letscho': ['letscho'],
            'Kren': ['kren', 'meerrettich'],
            'Aufstrich': ['aufstrich', 'grammel', 'liptauer'],
        },
        'Frühstück': {
            'Müsli': ['müsli', 'knusperli', 'knusper pur', 'oetker knusper'],
            'Cornflakes': ['cornflakes', 'color loops'],
            'Haferflocken': ['haferflocken', 'hafer'],
            'Kaffee': ['kaffee', 'nescafé', 'nescafe', 'crema intenso', 'hornig'],
            'Porridge': ['porridge'],
        },
        'Süßigkeiten & Snacks': {
            'Schokolade': ['schokolade', 'schoko', 'nutella', 'kinder-pingui', 'manner'],
            'Kekse': ['keks', 'biskuit', 'cookie', 'biskotten', 'leibniz', 'pick up'],
            'Chips': ['chips', 'snips', 'best foodies bio bunte'],
            'Nüsse': ['nuss', 'mandel', 'haselnuss', 'walnuss', 'walnüsse', 'cashew', 'pistazie', 'erdnuss',
                      'studentenfutter', 'studentenfutt', 'pinienkerne', 'sonnenblumenkerne', 'chiasamen'],
            'Trockenfrüchte': ['rosine', 'dattel', 'maroni'],
            'Süßigkeiten': ['tiramisu', 'duplo', 'suchard', 'celebrations', 'corny', 'trüffeltortenstück',
                            'sorger schwarzwälder', 'waffeleier'],
            'Proteinriegel': ['proteinriegel', 'barebells', 'neoh'],
            'Mohn': ['mohn'],
        },
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
        'Hygiene & Kosmetik': {
            'Shampoo': ['shampoo'],
            'Duschgel': ['duschgel', 'dusche'],
            'Deo': ['deo'],
            'Lippenpflege': ['lippenpflege'],
            'Zahnpflege': ['zahncreme', 'zahnspül', 'zahnpasta', 'colgate', 'blend-a-med', 'elmex', 'sensodyne',
                           'corega', 'zahnseide'],
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
            'Spülschwamm': ['spülschwamm', 'vileda', 'schwammtuch'],
            'Reinigungstücher': ['reinigungstücher', 'bi care'],
            'Feuchttücher': ['feucht', 'topa'],
            'Wundspray': ['wund reinigungsspr'],
        },
        'Tiefkühl': {
            'Tiefkühlkost': ['iglo', 'tk ', 'tiefkühl'],
            'Pizza': ['pizza', 'pizzamehl'],
            'Eis': ['eis ', 'cornetto', 'langnese', 'magnum', 'eskimo', 'cremissimo', 'mälzer&fu'],
            'Tortillas': ['tortilla', 'wrap', 'tex mex', 'corn&wheat'],
        },
        'Fertiggerichte': {
            'Suppen': ['suppe', 'rindsuppe', 'eierschöberl'],
            'Cornichons': ['cornichons'],
        },
        'Textilien & Non-Food': {
            'Textilien': ['thermohose', 'mütze', 'kissen'],
            'Blumen & Pflanzen': ['palmkätzchen', 'blühplfanzen', 'adventkranz', 'markttulpen', 'blumen'],
            'Batterien': ['batterien', 'batter', 'varta'],
            'Geschenke & Deko': ['bon ', 'geschenk', 'neujahrsguß', 'happy birthay'],
            'Lichterketten': ['lichterkette', 'lichter', 'magnet-lichter'],
            'Diverses': ['non food', 'abverkauf', 'aktion', 'mailing', 'limited edition', 'bonus'],
        },
        'Sonstiges': {
            'Pfandartikel': ['pfand', 'einwegpfand', 'pfandartikel', 'leergut', 'leergut-ret', 'leerflasche'],
            'Tragetaschen': ['tragetasche'],
            'Sonstiges': ['sonstiges', 'frisch gekocht', 'ready to eat', 'billa bon', 'äpp-only', 'unsere besten 6er',
                          '8 x nimm mehr', 'stifterl', 'schütt-streubehälter', 'tatü box', 'koro', 'bi good',
                          'gärtnerbund', 'lieblingsprodukt', 'bio gourmet', 'landfr', 'jö', 'rabattsammler',
                          'vorteilsbox', 'äpp extrem', 'teuerstes prod'],
        },
    }

    def finde_produktgruppe_und_ueberkategorie(produktname):
        """Findet automatisch passende Produktgruppe basierend auf Keywords"""
        if not produktname:
            return None, None

        name_lower = produktname.lower()

        for ueberkategorie, gruppen in PRODUKTGRUPPEN_MAP.items():
            for produktgruppe, keywords in gruppen.items():
                for keyword in keywords:
                    if keyword in name_lower:
                        return ueberkategorie, produktgruppe

        return None, None

    # GET: Anzeige der Mapper-Seite
    if request.method == 'GET':
        # Filter aus GET-Parametern
        suche = request.GET.get('suche', '')
        filter_typ = request.GET.get('filter', 'alle')
        ueberkategorie_filter = request.GET.get('ueberkategorie_filter', '')
        produktgruppe_filter = request.GET.get('produktgruppe_filter', '')

        # Basis-Queryset
        produkte = BillaProdukt.objects.all()

        # Suche
        if suche:
            produkte = produkte.filter(
                Q(name_normalisiert__icontains=suche) |
                Q(name_original__icontains=suche) |
                Q(name_korrigiert__icontains=suche)
            )

        # Status-Filter
        if filter_typ == 'mit':
            produkte = produkte.exclude(ueberkategorie__isnull=True)
        elif filter_typ == 'ohne':
            produkte = produkte.filter(ueberkategorie__isnull=True)

        # Überkategorie-Filter
        if ueberkategorie_filter:
            produkte = produkte.filter(ueberkategorie=ueberkategorie_filter)

        # Produktgruppe-Filter
        if produktgruppe_filter:
            produkte = produkte.filter(produktgruppe=produktgruppe_filter)

        # Pagination (100 Produkte pro Seite)
        from django.core.paginator import Paginator
        paginator = Paginator(produkte, 100)
        page_number = request.GET.get('page', 1)
        produkte_page = paginator.get_page(page_number)

        # Auto-Mapping für noch nicht zugeordnete Produkte
        # UND verfügbare Produktgruppen pro Produkt hinzufügen
        produkte_liste = []
        for produkt in produkte_page:  # Verwende produkte_page statt produkte
            if not produkt.ueberkategorie:
                ueberkat, prodgruppe = finde_produktgruppe_und_ueberkategorie(produkt.name_normalisiert)
                produkt.auto_ueberkategorie = ueberkat
                produkt.auto_produktgruppe = prodgruppe

            # Verfügbare Produktgruppen für dieses Produkt
            if produkt.ueberkategorie and produkt.ueberkategorie in PRODUKTGRUPPEN_MAP:
                produkt.verfuegbare_gruppen = list(PRODUKTGRUPPEN_MAP[produkt.ueberkategorie].keys())
            else:
                produkt.verfuegbare_gruppen = []

            produkte_liste.append(produkt)

        # Statistiken
        alle_produkte = BillaProdukt.objects.all()
        stats = {
            'gesamt': alle_produkte.count(),
            'mit_gruppe': alle_produkte.exclude(ueberkategorie__isnull=True).count(),
            'ohne_gruppe': alle_produkte.filter(ueberkategorie__isnull=True).count(),
        }

        # Konvertiere Map zu einfachem Dict für Template
        produktgruppen_simplified = {
            ueberkat: list(gruppen.keys())
            for ueberkat, gruppen in PRODUKTGRUPPEN_MAP.items()
        }

        context = {
            'produkte': produkte_liste,
            'page_obj': produkte_page,  # Für Pagination im Template
            'stats': stats,
            'suche': suche,
            'filter': filter_typ,
            'ueberkategorie_filter': ueberkategorie_filter,
            'produktgruppe_filter': produktgruppe_filter,
            'ueberkategorien': sorted(PRODUKTGRUPPEN_MAP.keys()),
            'produktgruppen_map': produktgruppen_simplified,
            'produktgruppen_json': json.dumps(produktgruppen_simplified),
        }

        return render(request, 'billa/billa_produktgruppen_mapper.html', context)

    # POST: Speichern der Änderungen
    elif request.method == 'POST':
        updated_count = 0

        # Sammle alle Produkt-IDs aus dem POST
        produkt_ids = set()
        for key in request.POST.keys():
            if key.startswith('ueberkategorie_'):
                produkt_ids.add(key.split('_')[1])

        # Bulk-Update für bessere Performance
        for produkt_id in produkt_ids:
            try:
                produkt = BillaProdukt.objects.get(id=produkt_id)

                # Neue Werte aus POST
                ueberkategorie = request.POST.get(f'ueberkategorie_{produkt_id}', '').strip()
                produktgruppe = request.POST.get(f'produktgruppe_{produkt_id}', '').strip()
                name_korrigiert = request.POST.get(f'name_korrigiert_{produkt_id}', '').strip()

                # Konvertiere leere Strings zu None
                ueberkategorie = ueberkategorie if ueberkategorie else None
                produktgruppe = produktgruppe if produktgruppe else None
                name_korrigiert = name_korrigiert if name_korrigiert else None

                # Prüfe ob sich was geändert hat
                changed = False
                if produkt.ueberkategorie != ueberkategorie:
                    produkt.ueberkategorie = ueberkategorie
                    changed = True
                if produkt.produktgruppe != produktgruppe:
                    produkt.produktgruppe = produktgruppe
                    changed = True
                if produkt.name_korrigiert != name_korrigiert:
                    produkt.name_korrigiert = name_korrigiert
                    changed = True

                if changed:
                    produkt.save()
                    updated_count += 1

            except BillaProdukt.DoesNotExist:
                continue

        if updated_count > 0:
            messages.success(request, f'✓ {updated_count} Produkte erfolgreich aktualisiert!')
        else:
            messages.info(request, 'Keine Änderungen vorgenommen.')

        # Bleibe auf der gleichen Seite mit den gleichen Filtern
        redirect_url = reverse('billa:billa_produktgruppen_mapper')
        if request.GET:
            redirect_url += '?' + request.GET.urlencode()
        return redirect(redirect_url)


@login_required
def billa_produktgruppen_liste(request):
    """Übersicht aller Produktgruppen mit aggregierten Daten"""

    # Icon-Mapping für Überkategorien
    KATEGORIE_ICONS = {
        'Gemüse': 'bi-basket',
        'Obst': 'bi-apple',
        'Milchprodukte': 'bi-cup-straw',
        'Fleisch & Wurst': 'bi-shop',
        'Getränke': 'bi-cup',
        'Brot & Gebäck': 'bi-bread-slice',
        'Tiefkühl': 'bi-snow',
        'Süßigkeiten': 'bi-candy',
        'Konserven': 'bi-archive',
        'Haushalt': 'bi-house',
        'Körperpflege': 'bi-droplet',
        'Sonstiges': 'bi-three-dots'
    }

    # Filter
    ueberkategorie_filter = request.GET.get('ueberkategorie')
    suche = request.GET.get('suche')
    sortierung = request.GET.get('sort', '-anzahl_kaeufe')

    # Aggregiere Daten nach Produktgruppe
    produktgruppen = BillaProdukt.objects.exclude(
        produktgruppe__isnull=True
    ).exclude(
        produktgruppe=''
    ).values(
        'produktgruppe', 'ueberkategorie'
    ).annotate(
        anzahl_produkte=Count('id'),
        anzahl_kaeufe=Sum('anzahl_kaeufe'),
        durchschnittspreis=Avg('durchschnittspreis'),
        aktueller_preis=Avg('letzter_preis')
    )

    # Filter nach Überkategorie
    if ueberkategorie_filter and ueberkategorie_filter != 'alle':
        produktgruppen = produktgruppen.filter(ueberkategorie=ueberkategorie_filter)

    # Suche
    if suche:
        produktgruppen = produktgruppen.filter(produktgruppe__icontains=suche)

    # Sortierung
    sortierung_map = {
        '-anzahl_kaeufe': '-anzahl_kaeufe',
        'anzahl_kaeufe': 'anzahl_kaeufe',
        '-durchschnittspreis': '-durchschnittspreis',
        'durchschnittspreis': 'durchschnittspreis',
        'produktgruppe': 'produktgruppe',
        '-produktgruppe': '-produktgruppe',
        '-anzahl_produkte': '-anzahl_produkte'
    }
    produktgruppen = produktgruppen.order_by(sortierung_map.get(sortierung, '-anzahl_kaeufe'))

    # Liste in Python umwandeln und Icons hinzufügen
    produktgruppen_list = []
    for gruppe in produktgruppen:
        gruppe['icon'] = KATEGORIE_ICONS.get(gruppe['ueberkategorie'], 'bi-box-seam')
        produktgruppen_list.append(gruppe)

    # Alle Überkategorien für Filter
    alle_ueberkategorien = BillaProdukt.objects.exclude(
        ueberkategorie__isnull=True
    ).values_list('ueberkategorie', flat=True).distinct().order_by('ueberkategorie')

    context = {
        'produktgruppen': produktgruppen_list,
        'ueberkategorien': list(alle_ueberkategorien),
        'selected_ueberkategorie': ueberkategorie_filter or 'alle',
        'suche': suche or '',
        'sortierung': sortierung,
        'gesamt_gruppen': len(produktgruppen_list)
    }

    return render(request, 'billa/billa_produktgruppen_liste.html', context)


@login_required
def billa_produktgruppe_detail(request, produktgruppe):
    """
    Detailansicht einer Produktgruppe mit integrierter Preisentwicklung
    ERWEITERT: Kombiniert normale Ansicht + Preisentwicklungs-Features
    """
    from decimal import Decimal
    from django.db.models import Q, Count, Sum, Avg, Min, Max

    # ========================================================================
    # BESTEHENDE LOGIK - Produkte und Basis-Daten
    # ========================================================================

    # Alle Produkte dieser Gruppe
    produkte = BillaProdukt.objects.filter(
        produktgruppe=produktgruppe
    ).annotate(
        gesamtausgaben=Sum('artikel__gesamtpreis')
    ).prefetch_related('preishistorie').order_by('-anzahl_kaeufe')

    if not produkte.exists():
        from django.http import Http404
        raise Http404("Produktgruppe nicht gefunden")

    # Überkategorie und Icon
    ueberkategorie = produkte.first().ueberkategorie
    KATEGORIE_ICONS = {
        'Gemüse': 'bi-basket',
        'Obst': 'bi-apple',
        'Milchprodukte': 'bi-cup-straw',
        'Fleisch & Wurst': 'bi-shop',
        'Getränke': 'bi-cup',
        'Brot & Gebäck': 'bi-bread-slice',
        'Tiefkühl': 'bi-snow',
        'Süßigkeiten': 'bi-candy',
        'Konserven': 'bi-archive',
        'Haushalt': 'bi-house',
        'Körperpflege': 'bi-droplet',
        'Sonstiges': 'bi-three-dots'
    }
    icon = KATEGORIE_ICONS.get(ueberkategorie, 'bi-box-seam')

    # Statistiken für die gesamte Gruppe
    stats = produkte.aggregate(
        gesamt_produkte=Count('id'),
        gesamt_kaeufe=Sum('anzahl_kaeufe'),
        durchschnittspreis=Avg('durchschnittspreis'),
        min_preis=Min('letzter_preis'),
        max_preis=Max('letzter_preis'),
        gesamt_ausgaben=Sum('gesamtausgaben')
    )

    # Letzte Käufe ALLER Produkte dieser Gruppe (mit Produktname)
    letzte_kaeufe = BillaArtikel.objects.filter(
        produkt__produktgruppe=produktgruppe
    ).select_related(
        'einkauf', 'produkt'
    ).order_by('-einkauf__datum')[:30]

    # ========================================================================
    # NEU: PREISENTWICKLUNG - Detaillierte Analyse
    # ========================================================================

    # 1. Berechne Preisänderungen für jedes Produkt
    produkte_mit_preisen = []

    for produkt in produkte:
        preis_stats = produkt.preishistorie.aggregate(
            min_preis=Min('preis'),
            max_preis=Max('preis'),
            count=Count('id')
        )

        # Nur Produkte mit mindestens 2 Preispunkten
        if preis_stats['count'] >= 2 and preis_stats['min_preis']:
            min_preis = preis_stats['min_preis']
            max_preis = preis_stats['max_preis']
            diff = max_preis - min_preis

            if min_preis > 0:
                diff_pct = (diff / min_preis * 100)
                produkte_mit_preisen.append({
                    'produkt': produkt,
                    'min_preis': min_preis,
                    'max_preis': max_preis,
                    'diff': diff,
                    'diff_pct': diff_pct
                })

    # Sortiere nach Preisänderung (größte Änderung zuerst)
    produkte_mit_preisen.sort(key=lambda x: x['diff_pct'], reverse=True)

    # 2. Preisentwicklung der gesamten Gruppe (erweitert mit min/max)
    preis_historie_gruppe = BillaPreisHistorie.objects.filter(
        produkt__produktgruppe=produktgruppe
    ).values('datum').annotate(
        durchschnitt=Avg('preis'),
        min_preis=Min('preis'),
        max_preis=Max('preis')
    ).order_by('datum')

    # ========================================================================
    # Context zusammenstellen
    # ========================================================================

    import json

    # Konvertiere Preis-Historie für Charts (JSON-serialisierbar)
    preis_historie_simple = []
    for entry in BillaPreisHistorie.objects.filter(
            produkt__produktgruppe=produktgruppe
    ).values('datum').annotate(
        durchschnitt=Avg('preis')
    ).order_by('datum'):
        preis_historie_simple.append({
            'datum': entry['datum'].strftime('%Y-%m-%d'),
            'durchschnitt': float(entry['durchschnitt']) if entry['durchschnitt'] else 0
        })

    # Konvertiere erweiterte Preis-Historie (mit min/max)
    preis_historie_detail = []
    for entry in preis_historie_gruppe:
        preis_historie_detail.append({
            'datum': entry['datum'].strftime('%Y-%m-%d'),
            'durchschnitt': float(entry['durchschnitt']) if entry['durchschnitt'] else 0,
            'min_preis': float(entry['min_preis']) if entry['min_preis'] else 0,
            'max_preis': float(entry['max_preis']) if entry['max_preis'] else 0
        })

    context = {
        # Bestehende Daten
        'produktgruppe': produktgruppe,
        'ueberkategorie': ueberkategorie,
        'icon': icon,
        'produkte': produkte,
        'stats': stats,
        'letzte_kaeufe': letzte_kaeufe,

        # NEU: Preisentwicklungs-Daten
        'produkte_mit_preisen': produkte_mit_preisen,

        # JSON-serialisierte Chart-Daten
        'preis_historie_json': json.dumps(preis_historie_simple),
        'preis_historie_detail_json': json.dumps(preis_historie_detail)
    }

    return render(request, 'billa/billa_produktgruppe_detail.html', context)


# ============================================================================
# PREISENTWICKLUNG - ÜBERKATEGORIEN
# ============================================================================

@login_required
def billa_ueberkategorien_liste(request):
    """
    Zeigt alle Überkategorien mit aggregierter Preisentwicklung.
    ✅ FIX: Konvertiert Decimal zu Float für JavaScript Charts
    """

    # Aggregiere Überkategorien direkt in der DB
    ueberkategorien_base = BillaProdukt.objects.exclude(
        Q(ueberkategorie__isnull=True) | Q(ueberkategorie='')
    ).values('ueberkategorie').annotate(
        anzahl_produkte=Count('id', distinct=True),
        anzahl_kaeufe=Sum('anzahl_kaeufe')
    ).order_by('ueberkategorie')

    # Berechne Preisentwicklung für jede Kategorie
    ueberkategorien = []

    for kat in ueberkategorien_base:
        kategorie_name = kat['ueberkategorie']

        # Preisentwicklung über Zeit
        preis_stats = BillaPreisHistorie.objects.filter(
            produkt__ueberkategorie=kategorie_name
        ).aggregate(
            min_preis=Min('preis'),
            max_preis=Max('preis'),
            avg_preis=Avg('preis'),
            count=Count('id')
        )

        # Nur Kategorien mit Preishistorie
        if preis_stats['count'] >= 2 and preis_stats['min_preis']:
            min_preis = preis_stats['min_preis']
            max_preis = preis_stats['max_preis']
            diff = max_preis - min_preis
            diff_pct = (diff / min_preis * 100) if min_preis > 0 else 0

            # Zeitreihe für Chart
            preis_historie_raw = BillaPreisHistorie.objects.filter(
                produkt__ueberkategorie=kategorie_name
            ).values('datum').annotate(
                durchschnitt=Avg('preis')
            ).order_by('datum')[:60]

            # ✅ FIX: Konvertiere Decimal zu Float für JavaScript
            preis_historie_converted = [
                {
                    'datum': h['datum'],
                    'durchschnitt': float(h['durchschnitt']) if h['durchschnitt'] else 0.0
                }
                for h in preis_historie_raw
            ]

            ueberkategorien.append({
                'name': kategorie_name,
                'anzahl_produkte': kat['anzahl_produkte'],
                'anzahl_kaeufe': kat['anzahl_kaeufe'] or 0,
                'min_preis': float(min_preis),  # ✅ Float conversion
                'max_preis': float(max_preis),  # ✅ Float conversion
                'avg_preis': float(preis_stats['avg_preis']) if preis_stats['avg_preis'] else 0.0,  # ✅ Float conversion
                'diff': float(diff),  # ✅ Float conversion
                'diff_pct': float(diff_pct),  # ✅ Float conversion
                'preis_historie': preis_historie_converted  # ✅ Alle Werte als Float
            })

    # Sortiere nach Preisänderung
    ueberkategorien.sort(key=lambda x: x['diff_pct'], reverse=True)

    context = {
        'ueberkategorien': ueberkategorien
    }

    return render(request, 'billa/billa_ueberkategorien_liste.html', context)


@login_required
def billa_ueberkategorie_detail(request, ueberkategorie):
    """
    Detailansicht einer Überkategorie mit integrierter Preisentwicklung
    NEU: Analog zu Produktgruppen und Marken mit Tab-Navigation
    """
    from decimal import Decimal
    from django.db.models import Q, Count, Sum, Avg, Min, Max
    import json

    # Prüfe ob Überkategorie existiert
    if not BillaProdukt.objects.filter(ueberkategorie=ueberkategorie).exists():
        from django.http import Http404
        raise Http404("Überkategorie nicht gefunden")

    # ========================================================================
    # PRODUKTGRUPPEN dieser Überkategorie
    # ========================================================================

    # Aggregiere Produktgruppen
    produktgruppen_base = BillaProdukt.objects.filter(
        ueberkategorie=ueberkategorie
    ).exclude(
        Q(produktgruppe__isnull=True) | Q(produktgruppe='')
    ).values('produktgruppe').annotate(
        anzahl_produkte=Count('id', distinct=True),
        anzahl_kaeufe=Sum('anzahl_kaeufe'),
        durchschnittspreis=Avg('durchschnittspreis')
    ).order_by('-anzahl_kaeufe')

    # Icons für Produktgruppen
    KATEGORIE_ICONS = {
        'Gemüse': 'bi-basket',
        'Obst': 'bi-apple',
        'Milchprodukte': 'bi-cup-straw',
        'Fleisch & Wurst': 'bi-shop',
        'Getränke': 'bi-cup',
        'Brot & Gebäck': 'bi-bread-slice',
        'Tiefkühl': 'bi-snow',
        'Süßigkeiten': 'bi-candy',
        'Konserven': 'bi-archive',
        'Haushalt': 'bi-house',
        'Körperpflege': 'bi-droplet',
        'Sonstiges': 'bi-three-dots'
    }
    icon = KATEGORIE_ICONS.get(ueberkategorie, 'bi-box-seam')

    produktgruppen_list = []
    for gruppe in produktgruppen_base:
        gruppe['icon'] = KATEGORIE_ICONS.get(ueberkategorie, 'bi-tag')
        produktgruppen_list.append(gruppe)

    # ========================================================================
    # STATISTIKEN der Überkategorie
    # ========================================================================

    stats = BillaProdukt.objects.filter(
        ueberkategorie=ueberkategorie
    ).aggregate(
        gesamt_produkte=Count('id', distinct=True),
        gesamt_kaeufe=Sum('anzahl_kaeufe'),
        durchschnittspreis=Avg('durchschnittspreis'),
        min_preis=Min('letzter_preis'),
        max_preis=Max('letzter_preis'),
        gesamt_ausgaben=Sum('artikel__gesamtpreis')
    )

    # ========================================================================
    # PREISENTWICKLUNG - Detaillierte Analyse
    # ========================================================================

    # 1. Produktgruppen mit Preisänderungen
    produktgruppen_mit_preisen = []

    for gruppe in produktgruppen_base:
        gruppe_name = gruppe['produktgruppe']

        # Preisentwicklung dieser Produktgruppe
        preis_stats = BillaPreisHistorie.objects.filter(
            produkt__ueberkategorie=ueberkategorie,
            produkt__produktgruppe=gruppe_name
        ).aggregate(
            min_preis=Min('preis'),
            max_preis=Max('preis'),
            avg_preis=Avg('preis'),
            count=Count('id')
        )

        # Nur Gruppen mit Preishistorie einbeziehen
        if preis_stats['count'] >= 2 and preis_stats['min_preis']:
            min_preis = preis_stats['min_preis']
            max_preis = preis_stats['max_preis']
            diff = max_preis - min_preis
            diff_pct = (diff / min_preis * 100) if min_preis > 0 else 0

            # ✅ NEU: Preisverlauf für Charts (letzte 30 Einträge)
            preis_historie_raw = BillaPreisHistorie.objects.filter(
                produkt__ueberkategorie=ueberkategorie,
                produkt__produktgruppe=gruppe_name
            ).values('datum').annotate(
                durchschnitt=Avg('preis')
            ).order_by('datum')[:30]

            preis_historie = [
                {
                    'datum': h['datum'].strftime('%d.%m.%Y'),
                    'durchschnitt': float(h['durchschnitt']) if h['durchschnitt'] else 0
                }
                for h in preis_historie_raw
            ]

            produktgruppen_mit_preisen.append({
                'name': gruppe_name,
                'anzahl_produkte': gruppe['anzahl_produkte'],
                'anzahl_kaeufe': gruppe['anzahl_kaeufe'],
                'min_preis': float(min_preis),  # ✅ Float für JSON
                'max_preis': float(max_preis),  # ✅ Float für JSON
                'avg_preis': float(preis_stats['avg_preis']) if preis_stats['avg_preis'] else 0,
                'diff': float(diff),  # ✅ Float für JSON
                'diff_pct': float(diff_pct),  # ✅ Float für JSON
                'preis_historie': preis_historie  # ✅ NEU: Für Charts
            })

    # Sortiere nach Preisänderung
    produktgruppen_mit_preisen.sort(key=lambda x: x['diff_pct'], reverse=True)

    # 2. Preisentwicklung der gesamten Überkategorie (erweitert mit min/max)
    preis_historie_kategorie = BillaPreisHistorie.objects.filter(
        produkt__ueberkategorie=ueberkategorie
    ).values('datum').annotate(
        durchschnitt=Avg('preis'),
        min_preis=Min('preis'),
        max_preis=Max('preis')
    ).order_by('datum')

    # JSON-serialisierbare Daten für Charts
    preis_historie_simple = []
    for entry in BillaPreisHistorie.objects.filter(
            produkt__ueberkategorie=ueberkategorie
    ).values('datum').annotate(
        durchschnitt=Avg('preis')
    ).order_by('datum'):
        preis_historie_simple.append({
            'datum': entry['datum'].strftime('%Y-%m-%d'),
            'durchschnitt': float(entry['durchschnitt']) if entry['durchschnitt'] else 0
        })

    # Konvertiere erweiterte Preis-Historie (mit min/max)
    preis_historie_detail = []
    for entry in preis_historie_kategorie:
        preis_historie_detail.append({
            'datum': entry['datum'].strftime('%Y-%m-%d'),
            'durchschnitt': float(entry['durchschnitt']) if entry['durchschnitt'] else 0,
            'min_preis': float(entry['min_preis']) if entry['min_preis'] else 0,
            'max_preis': float(entry['max_preis']) if entry['max_preis'] else 0
        })

    # ========================================================================
    # TOP PRODUKTE dieser Überkategorie
    # ========================================================================

    top_produkte = BillaProdukt.objects.filter(
        ueberkategorie=ueberkategorie
    ).order_by('-anzahl_kaeufe')[:10]

    # ========================================================================
    # Context zusammenstellen
    # ========================================================================

    stats['anzahl_produktgruppen'] = len(produktgruppen_list)

    context = {
        'ueberkategorie': ueberkategorie,
        'icon': icon,
        'stats': stats,
        'produktgruppen': produktgruppen_list,
        'produktgruppen_mit_preisen': json.dumps(produktgruppen_mit_preisen),  # ✅ JSON!
        'top_produkte': top_produkte,

        # JSON-serialisierte Chart-Daten
        'preis_historie_json': json.dumps(preis_historie_simple),
        'preis_historie_detail_json': json.dumps(preis_historie_detail)
    }

    return render(request, 'billa/billa_ueberkategorie_detail.html', context)



# ============================================================================
# MARKEN - ÜBERSICHT
# ============================================================================

@login_required
def billa_marken_liste(request):
    """
    Zeigt alle Marken mit Statistiken (analog zu Produktgruppen-Liste)
    """
    ueberkategorie_filter = request.GET.get('ueberkategorie', 'alle')
    produktgruppe_filter = request.GET.get('produktgruppe', 'alle')
    suche = request.GET.get('suche', '')
    sortierung = request.GET.get('sort', '-anzahl_kaeufe')

    # Aggregiere Daten nach Marke
    marken = BillaProdukt.objects.exclude(
        Q(marke__isnull=True) | Q(marke='')
    ).values(
        'marke'
    ).annotate(
        anzahl_produkte=Count('id'),
        anzahl_kaeufe=Sum('anzahl_kaeufe'),
        durchschnittspreis=Avg('durchschnittspreis'),
        aktueller_preis=Avg('letzter_preis')
    )

    # Filter nach Überkategorie
    if ueberkategorie_filter and ueberkategorie_filter != 'alle':
        marken = marken.filter(
            id__in=BillaProdukt.objects.filter(
                ueberkategorie=ueberkategorie_filter
            ).values_list('id', flat=True)
        )

    # Filter nach Produktgruppe
    if produktgruppe_filter and produktgruppe_filter != 'alle':
        marken = marken.filter(
            id__in=BillaProdukt.objects.filter(
                produktgruppe=produktgruppe_filter
            ).values_list('id', flat=True)
        )

    # Suche
    if suche:
        marken = marken.filter(marke__icontains=suche)

    # Sortierung
    sortierung_map = {
        '-anzahl_kaeufe': '-anzahl_kaeufe',
        'anzahl_kaeufe': 'anzahl_kaeufe',
        '-durchschnittspreis': '-durchschnittspreis',
        'durchschnittspreis': 'durchschnittspreis',
        'marke': 'marke',
        '-marke': '-marke',
        '-anzahl_produkte': '-anzahl_produkte',
        'anzahl_produkte': 'anzahl_produkte'
    }
    marken = marken.order_by(sortierung_map.get(sortierung, '-anzahl_kaeufe'))

    # Alle Überkategorien für Filter
    alle_ueberkategorien = BillaProdukt.objects.exclude(
        Q(marke__isnull=True) | Q(marke='')
    ).values_list('ueberkategorie', flat=True).distinct().exclude(
        ueberkategorie__isnull=True
    ).exclude(
        ueberkategorie=''
    ).order_by('ueberkategorie')

    # Alle Produktgruppen für Filter
    alle_produktgruppen = BillaProdukt.objects.exclude(
        Q(marke__isnull=True) | Q(marke='')
    ).values_list('produktgruppe', flat=True).distinct().exclude(
        produktgruppe__isnull=True
    ).exclude(
        produktgruppe=''
    ).order_by('produktgruppe')

    context = {
        'marken': list(marken),
        'ueberkategorien': list(alle_ueberkategorien),
        'produktgruppen': list(alle_produktgruppen),
        'selected_ueberkategorie': ueberkategorie_filter or 'alle',
        'selected_produktgruppe': produktgruppe_filter or 'alle',
        'suche': suche or '',
        'sortierung': sortierung,
        'gesamt_marken': marken.count()
    }

    return render(request, 'billa/billa_marken_liste.html', context)


# ============================================================================
# MARKEN - DETAIL
# ============================================================================

@login_required
def billa_marke_detail(request, marke):
    """
    Detailansicht einer spezifischen Marke mit integrierter Preisentwicklung
    ERWEITERT: Kombiniert normale Ansicht + Preisentwicklungs-Features
    """
    from decimal import Decimal
    from django.db.models import Q, Count, Sum, Avg, Min, Max
    import json

    # Prüfe ob Marke existiert
    if not BillaProdukt.objects.filter(marke=marke).exists():
        from django.http import Http404
        raise Http404("Marke nicht gefunden")

    # ========================================================================
    # BESTEHENDE LOGIK - Filter & Basis-Daten
    # ========================================================================

    # Filter aus Query-Parametern
    ueberkategorie_filter = request.GET.get('ueberkategorie', 'alle')
    produktgruppe_filter = request.GET.get('produktgruppe', 'alle')
    sortierung = request.GET.get('sort', '-anzahl_kaeufe')

    # Basis-Queryset
    produkte_base = BillaProdukt.objects.filter(marke=marke)

    # Filter anwenden
    produkte = produkte_base
    if ueberkategorie_filter and ueberkategorie_filter != 'alle':
        produkte = produkte.filter(ueberkategorie=ueberkategorie_filter)
    if produktgruppe_filter and produktgruppe_filter != 'alle':
        produkte = produkte.filter(produktgruppe=produktgruppe_filter)

    # Sortierung
    sortierung_map = {
        '-anzahl_kaeufe': '-anzahl_kaeufe',
        'anzahl_kaeufe': 'anzahl_kaeufe',
        '-durchschnittspreis': '-durchschnittspreis',
        'durchschnittspreis': 'durchschnittspreis',
        'name': 'name_normalisiert',
        '-name': '-name_normalisiert'
    }
    produkte = produkte.annotate(
        gesamtausgaben=Sum('artikel__gesamtpreis')
    ).order_by(sortierung_map.get(sortierung, '-anzahl_kaeufe')).prefetch_related('preishistorie')

    # Statistiken
    stats = produkte_base.aggregate(
        anzahl_produkte=Count('id'),
        gesamt_kaeufe=Sum('anzahl_kaeufe'),
        durchschnittspreis=Avg('durchschnittspreis'),
        gesamt_ausgaben=Sum('artikel__gesamtpreis')  # ✅ FIX: Nur ein Sum()
    )

    # Produktgruppen dieser Marke
    produktgruppen = produkte_base.exclude(
        Q(produktgruppe__isnull=True) | Q(produktgruppe='')
    ).values(
        'produktgruppe', 'ueberkategorie'
    ).annotate(
        anzahl_produkte=Count('id'),
        anzahl_kaeufe=Sum('anzahl_kaeufe')
    ).order_by('-anzahl_kaeufe')

    # Icons zu Produktgruppen hinzufügen
    KATEGORIE_ICONS = {
        'Gemüse': 'bi-basket',
        'Obst': 'bi-apple',
        'Milchprodukte': 'bi-cup-straw',
        'Fleisch & Wurst': 'bi-shop',
        'Getränke': 'bi-cup',
        'Brot & Gebäck': 'bi-bread-slice',
        'Tiefkühl': 'bi-snow',
        'Süßigkeiten': 'bi-candy',
        'Konserven': 'bi-archive',
        'Haushalt': 'bi-house',
        'Körperpflege': 'bi-droplet',
        'Sonstiges': 'bi-three-dots'
    }

    produktgruppen_list = []
    for gruppe in produktgruppen:
        gruppe['icon'] = KATEGORIE_ICONS.get(gruppe['ueberkategorie'], 'bi-tag')
        produktgruppen_list.append(gruppe)

    # Filter-Optionen
    alle_ueberkategorien = produkte_base.values_list(
        'ueberkategorie', flat=True
    ).distinct().exclude(
        ueberkategorie__isnull=True
    ).exclude(
        ueberkategorie=''
    ).order_by('ueberkategorie')

    alle_produktgruppen = produkte_base.values_list(
        'produktgruppe', flat=True
    ).distinct().exclude(
        produktgruppe__isnull=True
    ).exclude(
        produktgruppe=''
    ).order_by('produktgruppe')

    # ========================================================================
    # NEU: PREISENTWICKLUNG - Detaillierte Analyse
    # ========================================================================

    # 1. Berechne Preisänderungen für jedes Produkt
    produkte_mit_preisen = []

    for produkt in produkte:
        preis_stats = produkt.preishistorie.aggregate(
            min_preis=Min('preis'),
            max_preis=Max('preis'),
            count=Count('id')
        )

        # Nur Produkte mit mindestens 2 Preispunkten
        if preis_stats['count'] >= 2 and preis_stats['min_preis']:
            min_preis = preis_stats['min_preis']
            max_preis = preis_stats['max_preis']
            diff = max_preis - min_preis

            if min_preis > 0:
                diff_pct = (diff / min_preis * 100)
                produkte_mit_preisen.append({
                    'produkt': produkt,
                    'min_preis': min_preis,
                    'max_preis': max_preis,
                    'diff': diff,
                    'diff_pct': diff_pct
                })

    # Sortiere nach Preisänderung (größte Änderung zuerst)
    produkte_mit_preisen.sort(key=lambda x: x['diff_pct'], reverse=True)

    # 2. Preisentwicklung der gesamten Marke (erweitert mit min/max)
    preis_historie_marke = BillaPreisHistorie.objects.filter(
        produkt__marke=marke
    ).values('datum').annotate(
        durchschnitt=Avg('preis'),
        min_preis=Min('preis'),
        max_preis=Max('preis')
    ).order_by('datum')

    # JSON-serialisierbare Daten für Charts
    preis_historie_simple = []
    for entry in BillaPreisHistorie.objects.filter(
            produkt__marke=marke
    ).values('datum').annotate(
        durchschnitt=Avg('preis')
    ).order_by('datum'):
        preis_historie_simple.append({
            'datum': entry['datum'].strftime('%Y-%m-%d'),
            'durchschnitt': float(entry['durchschnitt']) if entry['durchschnitt'] else 0
        })

    # Konvertiere erweiterte Preis-Historie (mit min/max)
    preis_historie_detail = []
    for entry in preis_historie_marke:
        preis_historie_detail.append({
            'datum': entry['datum'].strftime('%Y-%m-%d'),
            'durchschnitt': float(entry['durchschnitt']) if entry['durchschnitt'] else 0,
            'min_preis': float(entry['min_preis']) if entry['min_preis'] else 0,
            'max_preis': float(entry['max_preis']) if entry['max_preis'] else 0
        })

    # ========================================================================
    # Context zusammenstellen
    # ========================================================================

    context = {
        # Bestehende Daten
        'marke': marke,
        'produkte': produkte,
        'stats': stats,
        'produktgruppen': produktgruppen_list,
        'ueberkategorien': list(alle_ueberkategorien),
        'alle_produktgruppen': list(alle_produktgruppen),
        'selected_ueberkategorie': ueberkategorie_filter or 'alle',
        'selected_produktgruppe': produktgruppe_filter or 'alle',
        'sortierung': sortierung,

        # NEU: Preisentwicklungs-Daten
        'produkte_mit_preisen': produkte_mit_preisen,

        # JSON-serialisierte Chart-Daten
        'preis_historie_json': json.dumps(preis_historie_simple),
        'preis_historie_detail_json': json.dumps(preis_historie_detail)
    }

    return render(request, 'billa/billa_marke_detail.html', context)