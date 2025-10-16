from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
import json
from django.db.models import Sum, Count, Q, Min, Max, Avg
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
import logging
from billa.models import (
    BillaArtikel, BillaProdukt, BillaPreisHistorie
)

logger = logging.getLogger(__name__)

@login_required
def billa_produkt_detail(request, produkt_id):
    """Detail-Ansicht eines Produkts mit Preisentwicklung"""
    produkt = get_object_or_404(BillaProdukt, pk=produkt_id)

    # ✅ Preisentwicklung als JSON
    preis_historie_raw = produkt.preishistorie.order_by('datum')

    preis_historie_json = [
        {
            'datum': h.datum.strftime('%Y-%m-%d'),
            'preis': float(h.preis),
            'menge': float(h.menge),
            'filiale': h.filiale.name if h.filiale else 'Unbekannt'  # ✅ String statt Objekt
        }
        for h in preis_historie_raw
    ]

    # Statistiken
    stats = produkt.artikel.aggregate(
        anzahl_kaeufe=Count('id'),
        min_preis=Min('preis_pro_einheit'),
        max_preis=Max('preis_pro_einheit'),
        avg_preis=Avg('preis_pro_einheit'),
        gesamt_ausgaben=Sum('gesamtpreis')
    )

    # Letzte Käufe
    letzte_kaeufe = produkt.artikel.select_related(
        'einkauf'
    ).order_by('-einkauf__datum')[:20]

    context = {
        'produkt': produkt,
        'preis_historie': json.dumps(preis_historie_json),  # ✅ JSON
        'stats': stats,
        'letzte_kaeufe': letzte_kaeufe
    }

    return render(request, 'billa/billa_produkt_detail.html', context)


@login_required
def billa_produkte_liste(request):
    """Liste aller Produkte mit Inline-Bearbeitung"""

    import json

    # Filter
    ueberkategorie = request.GET.get('ueberkategorie')
    suche = request.GET.get('suche')
    sortierung = request.GET.get('sort', '-anzahl_kaeufe')

    produkte = BillaProdukt.objects.all()

    # Filter nach Überkategorie
    if ueberkategorie and ueberkategorie != 'alle':
        produkte = produkte.filter(ueberkategorie=ueberkategorie)

    if suche:
        produkte = produkte.filter(
            Q(name_normalisiert__icontains=suche) |
            Q(name_original__icontains=suche)
        )

    produkte = produkte.order_by(sortierung)

    # Alle Überkategorien für Filter und Dropdowns
    alle_ueberkategorien = BillaProdukt.objects.values_list(
        'ueberkategorie', flat=True
    ).distinct().exclude(
        ueberkategorie__isnull=True
    ).exclude(
        ueberkategorie=''
    ).order_by('ueberkategorie')

    # Alle Produktgruppen für Dropdowns (gruppiert nach Überkategorie)
    produktgruppen_raw = BillaProdukt.objects.exclude(
        produktgruppe__isnull=True
    ).exclude(
        produktgruppe=''
    ).exclude(
        ueberkategorie__isnull=True
    ).exclude(
        ueberkategorie=''
    ).values('ueberkategorie', 'produktgruppe').distinct().order_by('ueberkategorie', 'produktgruppe')

    # Gruppiere Produktgruppen nach Überkategorie
    produktgruppen_by_ueberkategorie = {}
    for item in produktgruppen_raw:
        ukat = item['ueberkategorie']
        pgruppe = item['produktgruppe']
        if ukat not in produktgruppen_by_ueberkategorie:
            produktgruppen_by_ueberkategorie[ukat] = []
        if pgruppe not in produktgruppen_by_ueberkategorie[ukat]:
            produktgruppen_by_ueberkategorie[ukat].append(pgruppe)

    # Display-Name für ausgewählte Überkategorie
    selected_kategorie_display = 'Alle Kategorien'
    if ueberkategorie and ueberkategorie != 'alle':
        selected_kategorie_display = ueberkategorie

    context = {
        'produkte': produkte,
        'ueberkategorien': list(alle_ueberkategorien),
        'produktgruppen_by_ueberkategorie': json.dumps(produktgruppen_by_ueberkategorie),  # Als JSON
        'selected_ueberkategorie': ueberkategorie or 'alle',
        'selected_kategorie_display': selected_kategorie_display,
        'suche': suche or '',
        'sortierung': sortierung
    }

    return render(request, 'billa/billa_produkte_liste.html', context)


@login_required
def produktgruppen_mapper(request):
    """Produktgruppen-Mapping Tool"""

    # Alle Produkte mit relevanten Feldern holen
    produkte = BillaProdukt.objects.all().values(
        'id',
        'name_original',
        'name_normalisiert',
        'ueberkategorie',
        'produktgruppe'
    )

    context = {
        'produkte_json': json.dumps(list(produkte), ensure_ascii=False),
        'anzahl_produkte': len(produkte)
    }

    return render(request, 'billa/billa_produktgruppen_mapper.html', context)


@login_required
@require_POST
def produktgruppen_speichern(request):
    """Speichert die Produktgruppen-Zuordnung (inkl. Überkategorien)"""
    try:
        data = json.loads(request.body)
        produkte = data.get('produkte', [])

        updated_count = 0
        for produkt_data in produkte:
            result = BillaProdukt.objects.filter(id=produkt_data['id']).update(
                ueberkategorie=produkt_data.get('ueberkategorie'),  # NEU
                produktgruppe=produkt_data.get('produktgruppe')
            )
            updated_count += result

        return JsonResponse({
            'status': 'success',
            'updated': updated_count,
            'message': f'{updated_count} Produkte aktualisiert'
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)


# Füge diese Views zu finance/views_billa.py hinzu

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