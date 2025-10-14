# finance/views_billa.py

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Avg, Count, Max, Min, Q
from django.db.models.functions import TruncMonth, TruncDate
from django.http import JsonResponse
from datetime import datetime, timedelta
from decimal import Decimal
import json
from .models import (
    BillaEinkauf, BillaArtikel, BillaProdukt,
    BillaPreisHistorie
)
from django.views.decorators.http import require_POST

@login_required
def billa_dashboard(request):
    """Haupt-Dashboard für Billa-Analysen"""

    # Filter aus GET-Parametern
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    filiale = request.GET.get('filiale')

    # Basis-Queryset
    einkaufe = BillaEinkauf.objects.all()
    artikel = BillaArtikel.objects.select_related('einkauf', 'produkt')

    # Datum-Filter
    if start_date:
        einkaufe = einkaufe.filter(datum__gte=start_date)
        artikel = artikel.filter(einkauf__datum__gte=start_date)
    if end_date:
        einkaufe = einkaufe.filter(datum__lte=end_date)
        artikel = artikel.filter(einkauf__datum__lte=end_date)

    # Filialen-Filter
    if filiale and filiale != 'alle':
        einkaufe = einkaufe.filter(filiale=filiale)
        artikel = artikel.filter(einkauf__filiale=filiale)

    # Kennzahlen
    stats = einkaufe.aggregate(
        anzahl=Count('id'),
        gesamt_ausgaben=Sum('gesamt_preis'),
        gesamt_ersparnis=Sum('gesamt_ersparnis'),
        avg_warenkorb=Avg('gesamt_preis')
    )

    # Ausgaben im Zeitverlauf (täglich) - JSON-serialisierbar machen
    daily_spending_raw = einkaufe.annotate(
        tag=TruncDate('datum')
    ).values('tag').annotate(
        ausgaben=Sum('gesamt_preis')
    ).order_by('tag')

    # Konvertiere zu JSON-serialisierbarem Format
    daily_spending = [
        {
            'tag': item['tag'].strftime('%Y-%m-%d'),
            'ausgaben': float(item['ausgaben']) if item['ausgaben'] else 0
        }
        for item in daily_spending_raw
    ]

    # Ausgaben pro Monat - JSON-serialisierbar machen
    monthly_spending_raw = einkaufe.annotate(
        monat=TruncMonth('datum')
    ).values('monat').annotate(
        ausgaben=Sum('gesamt_preis'),
        ersparnis=Sum('gesamt_ersparnis'),
        anzahl=Count('id')
    ).order_by('monat')

    monthly_spending = [
        {
            'monat': item['monat'].strftime('%Y-%m'),
            'ausgaben': float(item['ausgaben']) if item['ausgaben'] else 0,
            'ersparnis': float(item['ersparnis']) if item['ersparnis'] else 0,
            'anzahl': item['anzahl']
        }
        for item in monthly_spending_raw
    ]

    # Top Produkte nach Häufigkeit - JSON-serialisierbar machen
    top_produkte_anzahl_raw = artikel.values(
        'produkt__name_normalisiert',
        'produkt__ueberkategorie'  # ← GEÄNDERT von kategorie
    ).annotate(
        anzahl=Count('id'),
        ausgaben=Sum('gesamtpreis')
    ).order_by('-anzahl')[:15]

    top_produkte_anzahl = [
        {
            'produkt__name_normalisiert': item['produkt__name_normalisiert'],
            'produkt__ueberkategorie': item['produkt__ueberkategorie'],  # ← GEÄNDERT
            'anzahl': item['anzahl'],
            'ausgaben': float(item['ausgaben']) if item['ausgaben'] else 0
        }
        for item in top_produkte_anzahl_raw
    ]

    # Top Produkte nach Ausgaben - JSON-serialisierbar machen
    top_produkte_ausgaben_raw = artikel.values(
        'produkt__name_normalisiert',
        'produkt__ueberkategorie'  # ← GEÄNDERT von kategorie
    ).annotate(
        ausgaben=Sum('gesamtpreis'),
        anzahl=Count('id')
    ).order_by('-ausgaben')[:15]

    top_produkte_ausgaben = [
        {
            'produkt__name_normalisiert': item['produkt__name_normalisiert'],
            'produkt__ueberkategorie': item['produkt__ueberkategorie'],  # ← GEÄNDERT
            'ausgaben': float(item['ausgaben']) if item['ausgaben'] else 0,
            'anzahl': item['anzahl']
        }
        for item in top_produkte_ausgaben_raw
    ]

    # Ausgaben nach Kategorie - JSON-serialisierbar machen
    ausgaben_kategorie_raw = artikel.values(
        'produkt__ueberkategorie'
    ).annotate(
        ausgaben=Sum('gesamtpreis')
    ).order_by('-ausgaben')

    ausgaben_kategorie = [
        {
            'produkt__ueberkategorie': item['produkt__ueberkategorie'],
            'ausgaben': float(item['ausgaben']) if item['ausgaben'] else 0
        }
        for item in ausgaben_kategorie_raw
    ]

    # Rabatte nach Typ - JSON-serialisierbar machen
    rabatte_raw = artikel.filter(
        rabatt__gt=0
    ).values('rabatt_typ').annotate(
        ersparnis=Sum('rabatt'),
        anzahl=Count('id')
    ).order_by('-ersparnis')

    rabatte = [
        {
            'rabatt_typ': item['rabatt_typ'],
            'ersparnis': float(item['ersparnis']) if item['ersparnis'] else 0,
            'anzahl': item['anzahl']
        }
        for item in rabatte_raw
    ]

    # Filialen für Filter
    filialen = BillaEinkauf.objects.values_list(
        'filiale', flat=True
    ).distinct().order_by('filiale')

    context = {
        'stats': stats,
        'daily_spending': json.dumps(daily_spending),  # JSON string für Template
        'monthly_spending': json.dumps(monthly_spending),
        'top_produkte_anzahl': json.dumps(top_produkte_anzahl),
        'top_produkte_ausgaben': json.dumps(top_produkte_ausgaben),
        'ausgaben_kategorie': json.dumps(ausgaben_kategorie),
        'rabatte': json.dumps(rabatte),
        'filialen': list(filialen),
        'selected_filiale': filiale or 'alle',
        'start_date': start_date,
        'end_date': end_date,
    }

    return render(request, 'finance/billa_dashboard.html', context)


@login_required
def billa_einkauf_detail(request, einkauf_id):
    """Detail-Ansicht eines Einkaufs"""
    einkauf = get_object_or_404(BillaEinkauf, pk=einkauf_id)
    artikel = einkauf.artikel.select_related('produkt').order_by('position')

    context = {
        'einkauf': einkauf,
        'artikel': artikel
    }

    return render(request, 'finance/billa_einkauf_detail.html', context)


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
            'filiale': h.filiale
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

    return render(request, 'finance/billa_produkt_detail.html', context)


@login_required
def billa_produkte_liste(request):
    """Liste aller Produkte"""

    # Filter
    ueberkategorie = request.GET.get('ueberkategorie')
    suche = request.GET.get('suche')
    sortierung = request.GET.get('sort', '-anzahl_kaeufe')

    produkte = BillaProdukt.objects.all()

    # Filter nach Überkategorie - GEÄNDERT
    if ueberkategorie and ueberkategorie != 'alle':
        produkte = produkte.filter(ueberkategorie=ueberkategorie)  # ← GEÄNDERT

    if suche:
        produkte = produkte.filter(
            Q(name_normalisiert__icontains=suche) |
            Q(name_original__icontains=suche)
        )

    produkte = produkte.order_by(sortierung)

    # Alle Überkategorien für Filter - NEU
    alle_ueberkategorien = BillaProdukt.objects.values_list(
        'ueberkategorie', flat=True
    ).distinct().exclude(
        ueberkategorie__isnull=True
    ).order_by('ueberkategorie')

    # Display-Name für ausgewählte Überkategorie
    selected_kategorie_display = 'Alle Kategorien'
    if ueberkategorie and ueberkategorie != 'alle':
        selected_kategorie_display = ueberkategorie

    context = {
        'produkte': produkte,
        'ueberkategorien': list(alle_ueberkategorien),  # ← NEU
        'selected_ueberkategorie': ueberkategorie or 'alle',  # ← GEÄNDERT
        'selected_kategorie_display': selected_kategorie_display,
        'suche': suche or '',
        'sortierung': sortierung
    }

    return render(request, 'finance/billa_produkte_liste.html', context)


@login_required
def billa_preisentwicklung(request):
    """Zeigt Produkte mit größten Preisänderungen"""

    # Produkte mit mindestens 3 Käufen
    produkte_mit_aenderungen = []

    for produkt in BillaProdukt.objects.filter(anzahl_kaeufe__gte=3):
        preise = list(produkt.preishistorie.values_list('preis', flat=True))
        if len(preise) >= 2:
            min_preis = min(preise)
            max_preis = max(preise)
            diff = max_preis - min_preis
            diff_pct = (diff / min_preis * 100) if min_preis > 0 else 0

            if diff > Decimal('0.5'):
                produkte_mit_aenderungen.append({
                    'produkt': produkt,
                    'min_preis': min_preis,
                    'max_preis': max_preis,
                    'diff': diff,
                    'diff_pct': diff_pct
                })

    produkte_mit_aenderungen.sort(key=lambda x: x['diff_pct'], reverse=True)

    context = {
        'produkte': produkte_mit_aenderungen[:50]
    }

    return render(request, 'finance/billa_preisentwicklung.html', context)


@login_required
def billa_statistiken(request):
    """Erweiterte Statistiken und Analysen"""

    from django.db.models.functions import ExtractWeekDay, ExtractHour

    # Ausgaben nach Wochentag
    ausgaben_wochentag = BillaEinkauf.objects.annotate(
        wochentag=ExtractWeekDay('datum')
    ).values('wochentag').annotate(
        ausgaben=Sum('gesamt_preis'),
        anzahl=Count('id')
    ).order_by('wochentag')

    wochentage = {
        1: 'Sonntag', 2: 'Montag', 3: 'Dienstag', 4: 'Mittwoch',
        5: 'Donnerstag', 6: 'Freitag', 7: 'Samstag'
    }

    for item in ausgaben_wochentag:
        item['name'] = wochentage.get(item['wochentag'], '')

    # Ausgaben nach Uhrzeit
    ausgaben_stunde = BillaEinkauf.objects.filter(
        zeit__isnull=False
    ).annotate(
        stunde=ExtractHour('zeit')
    ).values('stunde').annotate(
        ausgaben=Sum('gesamt_preis'),
        anzahl=Count('id')
    ).order_by('stunde')

    # Durchschnittlicher Warenkorbwert nach Filiale
    ausgaben_filiale = BillaEinkauf.objects.values(
        'filiale'
    ).annotate(
        ausgaben=Sum('gesamt_preis'),
        anzahl=Count('id'),
        avg_warenkorb=Avg('gesamt_preis')
    ).order_by('-ausgaben')

    # Artikel pro Einkauf
    artikel_pro_einkauf = BillaEinkauf.objects.annotate(
        anzahl_artikel=Count('artikel')
    ).values('anzahl_artikel').annotate(
        anzahl_einkaufe=Count('id')
    ).order_by('anzahl_artikel')

    context = {
        'ausgaben_wochentag': list(ausgaben_wochentag),
        'ausgaben_stunde': list(ausgaben_stunde),
        'ausgaben_filiale': list(ausgaben_filiale),
        'artikel_pro_einkauf': list(artikel_pro_einkauf)
    }

    return render(request, 'finance/billa_statistiken.html', context)


# API Endpoints für AJAX

@login_required
def billa_api_preisverlauf(request, produkt_id):
    """API: Preisverlauf eines Produkts"""
    produkt = get_object_or_404(BillaProdukt, pk=produkt_id)

    preis_historie = produkt.preishistorie.order_by('datum').values(
        'datum', 'preis', 'filiale'
    )

    data = {
        'produkt': produkt.name_normalisiert,
        'historie': list(preis_historie)
    }

    return JsonResponse(data)


@login_required
def billa_api_stats(request):
    """API: Aktuelle Statistiken"""

    heute = datetime.now().date()
    vor_30_tagen = heute - timedelta(days=30)

    einkaufe = BillaEinkauf.objects.filter(datum__gte=vor_30_tagen)

    stats = einkaufe.aggregate(
        anzahl=Count('id'),
        ausgaben=Sum('gesamt_preis'),
        ersparnis=Sum('gesamt_ersparnis')
    )

    return JsonResponse(stats)

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

    return render(request, 'finance/produktgruppen_mapper.html', context)


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

    return render(request, 'finance/billa_produktgruppen_liste.html', context)


@login_required
def billa_produktgruppe_detail(request, produktgruppe):
    """Detailansicht einer Produktgruppe"""

    # Alle Produkte dieser Gruppe
    produkte = BillaProdukt.objects.filter(
        produktgruppe=produktgruppe
    ).annotate(
        gesamtausgaben=Sum('artikel__gesamtpreis')
    ).order_by('-anzahl_kaeufe')

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

    # Preisentwicklung über Zeit (Durchschnitt der Gruppe)
    preis_historie = BillaPreisHistorie.objects.filter(
        produkt__produktgruppe=produktgruppe
    ).values('datum').annotate(
        durchschnitt=Avg('preis')
    ).order_by('datum')

    context = {
        'produktgruppe': produktgruppe,
        'ueberkategorie': ueberkategorie,
        'icon': icon,
        'produkte': produkte,
        'stats': stats,
        'letzte_kaeufe': letzte_kaeufe,
        'preis_historie': list(preis_historie)
    }

    return render(request, 'finance/billa_produktgruppe_detail.html', context)


# ============================================================================
# PREISENTWICKLUNG - ÜBERSICHT
# ============================================================================

@login_required
def billa_preisentwicklung_uebersicht(request):
    """
    Übersichtsseite für Preisentwicklung.
    Zeigt aggregierte Statistiken für alle Ebenen.
    """

    # === Überkategorien Statistiken ===
    ueberkategorien_stats = BillaProdukt.objects.exclude(
        Q(ueberkategorie__isnull=True) | Q(ueberkategorie='')
    ).values('ueberkategorie').annotate(
        anzahl_produkte=Count('id'),
        anzahl_kaeufe=Sum('anzahl_kaeufe'),
        avg_preis=Avg('durchschnittspreis')
    ).order_by('-anzahl_kaeufe')[:10]

    # === Produktgruppen Statistiken (Top 20) ===
    produktgruppen_stats = BillaProdukt.objects.exclude(
        Q(produktgruppe__isnull=True) | Q(produktgruppe='')
    ).values('produktgruppe', 'ueberkategorie').annotate(
        anzahl_produkte=Count('id'),
        anzahl_kaeufe=Sum('anzahl_kaeufe'),
        avg_preis=Avg('durchschnittspreis')
    ).order_by('-anzahl_kaeufe')[:20]

    # === Top Preisänderungen (effizient berechnet) ===
    produkte_mit_preisen = []

    # Hole nur Produkte mit mindestens 3 Käufen
    relevante_produkte = BillaProdukt.objects.filter(
        anzahl_kaeufe__gte=3
    ).prefetch_related('preishistorie')[:100]  # Limitiere für Performance

    for produkt in relevante_produkte:
        # Hole Min/Max direkt aus PreisHistorie
        preis_stats = produkt.preishistorie.aggregate(
            min_preis=Min('preis'),
            max_preis=Max('preis'),
            count=Count('id')
        )

        if preis_stats['count'] >= 2 and preis_stats['min_preis'] and preis_stats['max_preis']:
            min_preis = preis_stats['min_preis']
            max_preis = preis_stats['max_preis']
            diff = max_preis - min_preis

            if diff > Decimal('0.5') and min_preis > 0:
                diff_pct = (diff / min_preis * 100)
                produkte_mit_preisen.append({
                    'produkt': produkt,
                    'min_preis': min_preis,
                    'max_preis': max_preis,
                    'diff': diff,
                    'diff_pct': diff_pct
                })

    # Sortiere nach Preisänderung
    produkte_mit_preisen.sort(key=lambda x: x['diff_pct'], reverse=True)

    context = {
        'ueberkategorien': ueberkategorien_stats,
        'produktgruppen': produktgruppen_stats,
        'top_produkte': produkte_mit_preisen[:20]
    }

    return render(request, 'finance/billa_preisentwicklung_uebersicht.html', context)


# ============================================================================
# PREISENTWICKLUNG - ÜBERKATEGORIEN
# ============================================================================

@login_required
def billa_preisentwicklung_ueberkategorien(request):
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

    return render(request, 'finance/billa_preisentwicklung_ueberkategorien.html', context)


# ============================================================================
# PREISENTWICKLUNG - EINZELNE ÜBERKATEGORIE (mit Produktgruppen)
# ============================================================================

@login_required
def billa_preisentwicklung_ueberkategorie(request, ueberkategorie):
    """Überkategorie mit Produktgruppen - MIT CHARTS"""

    stats = BillaProdukt.objects.filter(
        ueberkategorie=ueberkategorie
    ).aggregate(
        gesamt_produkte=Count('id', distinct=True),
        gesamt_kaeufe=Sum('anzahl_kaeufe'),
        durchschnittspreis=Avg('durchschnittspreis')
    )

    produktgruppen_base = BillaProdukt.objects.filter(
        ueberkategorie=ueberkategorie
    ).exclude(
        Q(produktgruppe__isnull=True) | Q(produktgruppe='')
    ).values('produktgruppe').annotate(
        anzahl_produkte=Count('id', distinct=True),
        anzahl_kaeufe=Sum('anzahl_kaeufe')
    ).order_by('produktgruppe')

    produktgruppen = []

    for gruppe in produktgruppen_base:
        gruppe_name = gruppe['produktgruppe']

        preis_stats = BillaPreisHistorie.objects.filter(
            produkt__ueberkategorie=ueberkategorie,
            produkt__produktgruppe=gruppe_name
        ).aggregate(
            min_preis=Min('preis'),
            max_preis=Max('preis'),
            count=Count('id')
        )

        if preis_stats['count'] >= 2 and preis_stats['min_preis']:
            min_preis = float(preis_stats['min_preis'])
            max_preis = float(preis_stats['max_preis'])
            diff = max_preis - min_preis
            diff_pct = (diff / min_preis * 100) if min_preis > 0 else 0

            preis_historie_raw = BillaPreisHistorie.objects.filter(
                produkt__ueberkategorie=ueberkategorie,
                produkt__produktgruppe=gruppe_name
            ).values('datum').annotate(
                durchschnitt=Avg('preis')
            ).order_by('datum')[:30]

            preis_historie = [
                {
                    'datum': h['datum'].strftime('%d.%m.%Y'),
                    'durchschnitt': float(h['durchschnitt'])
                }
                for h in preis_historie_raw
            ]

            produktgruppen.append({
                'name': gruppe_name,
                'anzahl_produkte': gruppe['anzahl_produkte'],
                'anzahl_kaeufe': gruppe['anzahl_kaeufe'],
                'min_preis': min_preis,
                'max_preis': max_preis,
                'diff': diff,
                'diff_pct': diff_pct,
                'preis_historie': preis_historie
            })

    produktgruppen.sort(key=lambda x: x['diff_pct'], reverse=True)

    context = {
        'ueberkategorie': ueberkategorie,
        'stats': stats,
        'produktgruppen': json.dumps(produktgruppen)
    }

    return render(request, 'finance/billa_preisentwicklung_ueberkategorie.html', context)


# ============================================================================
# PREISENTWICKLUNG - PRODUKTGRUPPE (mit einzelnen Produkten)
# ============================================================================

@login_required
def billa_preisentwicklung_produktgruppe(request, produktgruppe):
    """Produktgruppe Detail mit Preisentwicklung"""

    # Finde Überkategorie
    beispiel_produkt = BillaProdukt.objects.filter(
        produktgruppe=produktgruppe
    ).first()

    ueberkategorie = beispiel_produkt.ueberkategorie if beispiel_produkt else None

    # Alle Produkte
    produkte_queryset = BillaProdukt.objects.filter(
        produktgruppe=produktgruppe
    ).prefetch_related('preishistorie')

    # Berechne Preisänderungen
    produkte_mit_aenderungen = []

    for produkt in produkte_queryset:
        preis_stats = produkt.preishistorie.aggregate(
            min_preis=Min('preis'),
            max_preis=Max('preis'),
            count=Count('id')
        )

        if preis_stats['count'] >= 2 and preis_stats['min_preis']:
            min_preis = float(preis_stats['min_preis'])
            max_preis = float(preis_stats['max_preis'])
            diff = max_preis - min_preis
            diff_pct = (diff / min_preis * 100) if min_preis > 0 else 0

            produkte_mit_aenderungen.append({
                'produkt_id': produkt.id,
                'produkt_name': produkt.name_normalisiert,
                'anzahl_kaeufe': produkt.anzahl_kaeufe,
                'min_preis': min_preis,
                'max_preis': max_preis,
                'diff': diff,
                'diff_pct': diff_pct
            })

    produkte_mit_aenderungen.sort(key=lambda x: x['diff_pct'], reverse=True)

    # Preisentwicklung der Gruppe
    preis_historie_raw = BillaPreisHistorie.objects.filter(
        produkt__produktgruppe=produktgruppe
    ).values('datum').annotate(
        durchschnitt=Avg('preis')
    ).order_by('datum')

    # ✅ Konvertiere zu JSON-Format
    preis_historie_gruppe = [
        {
            'datum': h['datum'].strftime('%Y-%m-%d'),
            'durchschnitt': float(h['durchschnitt'])
        }
        for h in preis_historie_raw
    ]

    # Stats
    stats = produkte_queryset.aggregate(
        gesamt_produkte=Count('id'),
        gesamt_kaeufe=Sum('anzahl_kaeufe'),
        durchschnittspreis=Avg('durchschnittspreis')
    )

    context = {
        'produktgruppe': produktgruppe,
        'ueberkategorie': ueberkategorie,
        'produkte': json.dumps(produkte_mit_aenderungen),  # ✅ JSON
        'preis_historie_gruppe': json.dumps(preis_historie_gruppe),  # ✅ JSON
        'stats': stats
    }

    return render(request, 'finance/billa_preisentwicklung_produktgruppe.html', context)


# ============================================================================
# PREISENTWICKLUNG - EINZELNES PRODUKT
# ============================================================================

@login_required
def billa_preisentwicklung_produkt(request, produkt_id):
    """Einzelprodukt Detail mit Preisentwicklung"""

    produkt = get_object_or_404(BillaProdukt, pk=produkt_id)

    # Preisentwicklung
    preis_historie_raw = produkt.preishistorie.order_by('datum')

    # ✅ Konvertiere zu JSON
    preis_historie = [
        {
            'datum': h.datum.strftime('%Y-%m-%d'),
            'preis': float(h.preis),
            'menge': float(h.menge),
            'filiale': h.filiale
        }
        for h in preis_historie_raw
    ]

    # Statistiken
    stats = produkt.preishistorie.aggregate(
        anzahl_datenpunkte=Count('id'),
        min_preis=Min('preis'),
        max_preis=Max('preis'),
        avg_preis=Avg('preis')
    )

    # Kaufstatistiken
    kauf_stats = produkt.artikel.aggregate(
        anzahl_kaeufe=Count('id'),
        gesamt_ausgaben=Sum('gesamtpreis'),
        gesamt_menge=Sum('menge')
    )

    if stats['min_preis']:
        stats['min_preis'] = float(stats['min_preis'])
        stats['max_preis'] = float(stats['max_preis'])
        stats['avg_preis'] = float(stats['avg_preis'])
        diff = stats['max_preis'] - stats['min_preis']
        stats['diff'] = diff
        stats['diff_pct'] = (diff / stats['min_preis'] * 100) if stats['min_preis'] > 0 else 0

    stats.update(kauf_stats)

    # Letzte Käufe
    letzte_kaeufe = produkt.artikel.select_related('einkauf').order_by('-einkauf__datum')[:20]

    context = {
        'produkt': produkt,
        'preis_historie': json.dumps(preis_historie),
        'stats': stats,
        'letzte_kaeufe': letzte_kaeufe
    }

    return render(request, 'finance/billa_preisentwicklung_produkt.html', context)


# ============================================================================
# HILFSFUNKTIONEN
# ============================================================================

def calculate_price_change(queryset):
    """
    Berechnet Preisänderung für ein Queryset von Preishistorie.

    Args:
        queryset: QuerySet von BillaPreisHistorie

    Returns:
        dict mit min_preis, max_preis, diff, diff_pct oder None
    """
    stats = queryset.aggregate(
        min_preis=Min('preis'),
        max_preis=Max('preis'),
        count=Count('id')
    )

    if stats['count'] >= 2 and stats['min_preis'] and stats['max_preis']:
        min_preis = stats['min_preis']
        max_preis = stats['max_preis']
        diff = max_preis - min_preis
        diff_pct = (diff / min_preis * 100) if min_preis > 0 else 0

        return {
            'min_preis': min_preis,
            'max_preis': max_preis,
            'diff': diff,
            'diff_pct': diff_pct,
            'has_data': True
        }

    return {'has_data': False}