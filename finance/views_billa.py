# finance/views_billa.py
from django.db import transaction
from django.contrib import messages
import tempfile
import os
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Avg, Count, Max, Min, Q
from django.db.models.functions import TruncMonth, TruncDate
from django.http import JsonResponse
from datetime import datetime, timedelta
from decimal import Decimal
import json
from .models import (
    BillaEinkauf, BillaArtikel, BillaProdukt,
    BillaPreisHistorie, BillaFiliale
)
from django.views.decorators.http import require_POST
import pdfplumber
import re
from finance.brand_mapper import BrandMapper
from finance.billa_parser import BillaReceiptParser


@login_required
def billa_dashboard(request):
    """Haupt-Dashboard für Billa-Analysen"""

    # Filter aus GET-Parametern
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    filiale_id = request.GET.get('filiale')

    # Basis-Queryset
    einkaufe = BillaEinkauf.objects.select_related('filiale')
    artikel = BillaArtikel.objects.select_related('einkauf__filiale', 'produkt')

    # Datum-Filter
    if start_date:
        einkaufe = einkaufe.filter(datum__gte=start_date)
        artikel = artikel.filter(einkauf__datum__gte=start_date)
    if end_date:
        einkaufe = einkaufe.filter(datum__lte=end_date)
        artikel = artikel.filter(einkauf__datum__lte=end_date)

    # Filialen-Filter
    if filiale_id and filiale_id != 'alle':
        einkaufe = einkaufe.filter(filiale__filial_nr=filiale_id)
        artikel = artikel.filter(einkauf__filiale__filial_nr=filiale_id)

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

    # ========================================
    # NEU: Monatliche Ausgaben nach Überkategorie (für gestapeltes Diagramm)
    # ========================================
    monthly_by_group_raw = artikel.annotate(
        monat=TruncMonth('einkauf__datum')
    ).values('monat', 'produkt__ueberkategorie').annotate(
        ausgaben=Sum('gesamtpreis')
    ).order_by('monat', 'produkt__ueberkategorie')

    # Strukturiere Daten: {monat: {ueberkategorie: ausgaben}}
    monthly_data = {}
    all_ueberkategorien = set()

    for item in monthly_by_group_raw:
        monat_str = item['monat'].strftime('%Y-%m') if item['monat'] else 'Unbekannt'
        ueberkategorie = item['produkt__ueberkategorie'] or 'Ohne Kategorie'
        ausgaben = float(item['ausgaben']) if item['ausgaben'] else 0

        if monat_str not in monthly_data:
            monthly_data[monat_str] = {}

        monthly_data[monat_str][ueberkategorie] = ausgaben
        all_ueberkategorien.add(ueberkategorie)

    # Berechne Gesamtausgaben pro Überkategorie
    kategorie_totals = {}
    for kat in all_ueberkategorien:
        kategorie_totals[kat] = sum(
            monthly_data.get(m, {}).get(kat, 0)
            for m in monthly_data.keys()
        )

    # Sortiere nach Gesamtausgaben (absteigend - größte zuerst)
    ueberkategorien_sorted = sorted(
        all_ueberkategorien,
        key=lambda kat: kategorie_totals[kat],
        reverse=True  # Größte Ausgaben zuerst
    )

    # Pareto-Prinzip: Finde Top-Kategorien die ~80% ausmachen
    gesamt_ausgaben = sum(kategorie_totals.values())
    kumulativ = 0
    top_kategorien = []

    for kat in ueberkategorien_sorted:
        kumulativ += kategorie_totals[kat]
        top_kategorien.append(kat)
        # Stoppe bei 80% ODER maximal 8 Kategorien
        if kumulativ >= gesamt_ausgaben * 0.80 or len(top_kategorien) >= 8:
            break

    # Alle restlichen Kategorien
    sonstige_kategorien = [k for k in ueberkategorien_sorted if k not in top_kategorien]

    # Erstelle strukturierte Daten für Plotly
    # WICHTIG: In Plotly ist der erste Trace UNTEN im gestapelten Diagramm
    # Also: Größte Kategorie zuerst = unten, kleinste zuletzt = oben
    alle_monate = sorted(monthly_data.keys())

    # Kategorien-Reihenfolge für Plotly (größte zuerst = unten im Chart)
    kategorien_for_chart = top_kategorien.copy()

    # "Sonstiges" kommt ans Ende (= oben im Chart)
    if sonstige_kategorien:
        kategorien_for_chart.append('Sonstiges')

    monthly_spending_stacked = {
        'monate': alle_monate,
        'kategorien': kategorien_for_chart,
        'daten': {}
    }

    # Daten für Top-Kategorien
    for kat in top_kategorien:
        monthly_spending_stacked['daten'][kat] = [
            monthly_data.get(monat, {}).get(kat, 0)
            for monat in alle_monate
        ]

    # Summiere "Sonstiges" wenn vorhanden
    if sonstige_kategorien:
        monthly_spending_stacked['daten']['Sonstiges'] = [
            sum(monthly_data.get(monat, {}).get(kat, 0) for kat in sonstige_kategorien)
            for monat in alle_monate
        ]

    # ========================================
    # Alte monatliche Ausgaben (Gesamt) - für Backup/Vergleich
    # ========================================
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
        'produkt__ueberkategorie'
    ).annotate(
        anzahl=Count('id'),
        ausgaben=Sum('gesamtpreis')
    ).order_by('-anzahl')[:15]

    top_produkte_anzahl = [
        {
            'produkt__name_normalisiert': item['produkt__name_normalisiert'],
            'produkt__ueberkategorie': item['produkt__ueberkategorie'],
            'anzahl': item['anzahl'],
            'ausgaben': float(item['ausgaben']) if item['ausgaben'] else 0
        }
        for item in top_produkte_anzahl_raw
    ]

    # Top Produkte nach Ausgaben - JSON-serialisierbar machen
    top_produkte_ausgaben_raw = artikel.values(
        'produkt__name_normalisiert',
        'produkt__ueberkategorie'
    ).annotate(
        ausgaben=Sum('gesamtpreis'),
        anzahl=Count('id')
    ).order_by('-ausgaben')[:15]

    top_produkte_ausgaben = [
        {
            'produkt__name_normalisiert': item['produkt__name_normalisiert'],
            'produkt__ueberkategorie': item['produkt__ueberkategorie'],
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
    filialen = BillaFiliale.objects.filter(aktiv=True).order_by('filial_nr')

    # In der billa_dashboard View:
    # Marken-Statistiken
    anzahl_marken = BillaProdukt.objects.exclude(
        Q(marke__isnull=True) | Q(marke='')
    ).values('marke').distinct().count()

    # Top 5 Marken nach Käufen
    top_marken = BillaProdukt.objects.exclude(
        Q(marke__isnull=True) | Q(marke='')
    ).values('marke').annotate(
        anzahl_kaeufe=Sum('anzahl_kaeufe')
    ).order_by('-anzahl_kaeufe')[:5]


    context = {
        'stats': stats,
        'daily_spending': json.dumps(daily_spending),
        'monthly_spending': json.dumps(monthly_spending),  # Alte Daten (Backup)
        'monthly_spending_stacked': json.dumps(monthly_spending_stacked),  # NEU
        'top_produkte_anzahl': json.dumps(top_produkte_anzahl),
        'top_produkte_ausgaben': json.dumps(top_produkte_ausgaben),
        'ausgaben_kategorie': json.dumps(ausgaben_kategorie),
        'rabatte': json.dumps(rabatte),
        'filialen': filialen,
        'selected_filiale': filiale_id or 'alle',
        'start_date': start_date,
        'end_date': end_date,
        'anzahl_marken': anzahl_marken,
        'top_marken': top_marken,
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

    return render(request, 'finance/billa_produkt_detail.html', context)


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

    return render(request, 'finance/billa_produkte_liste.html', context)

# ❌ DEPRECATED
"""
@login_required
def billa_preisentwicklung(request):


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
"""

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

    return render(request, 'finance/billa_produktgruppe_detail.html', context)


# ============================================================================
# PREISENTWICKLUNG - ÜBERSICHT
# DEPRECATED - ersetzt durch billa_ueberkategorien
# ============================================================================
"""
@login_required
def billa_preisentwicklung_uebersicht(request):


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

    return render(request, 'finance/_OLD_billa_preisentwicklung_uebersicht.html', context)
"""

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

    return render(request, 'finance/billa_ueberkategorien_liste.html', context)


# ============================================================================
# PREISENTWICKLUNG - EINZELNE ÜBERKATEGORIE (mit Produktgruppen)
# ============================================================================

@login_required
def billa_ueberkategorie(request, ueberkategorie):
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

    return render(request, 'finance/billa_ueberkategorie.html', context)


# ============================================================================
# PREISENTWICKLUNG - PRODUKTGRUPPE (mit einzelnen Produkten)
# ❌ DEPRECATED - Funktionalität jetzt in billa_produktgruppe_detail integriert
# ============================================================================

"""
@login_required
def billa_preisentwicklung_produktgruppe(request, produktgruppe):

    # Finde Überkategorie dieser Produktgruppe
    beispiel_produkt = BillaProdukt.objects.filter(
        produktgruppe=produktgruppe
    ).first()

    ueberkategorie = beispiel_produkt.ueberkategorie if beispiel_produkt else None

    # === Alle Produkte dieser Gruppe ===
    produkte_queryset = BillaProdukt.objects.filter(
        produktgruppe=produktgruppe
    ).prefetch_related('preishistorie')

    # === Berechne Preisänderungen für jedes Produkt (JSON-serialisierbar) ===
    produkte_mit_aenderungen = []

    for produkt in produkte_queryset:
        preis_stats = produkt.preishistorie.aggregate(
            min_preis=Min('preis'),
            max_preis=Max('preis'),
            count=Count('id')
        )

        if preis_stats['count'] >= 2 and preis_stats['min_preis']:
            min_preis = preis_stats['min_preis']
            max_preis = preis_stats['max_preis']
            diff = max_preis - min_preis

            if min_preis > 0:
                diff_pct = (diff / min_preis * 100)
                # ✅ KORRIGIERT: Serialisiere alle Werte als Float/String
                produkte_mit_aenderungen.append({
                    'produkt': {
                        'id': produkt.id,
                        'name_normalisiert': produkt.name_normalisiert,
                        'marke': produkt.marke or '',
                        'anzahl_kaeufe': produkt.anzahl_kaeufe or 0,
                        'durchschnittspreis': float(produkt.durchschnittspreis) if produkt.durchschnittspreis else 0.0,
                    },
                    'min_preis': float(min_preis),
                    'max_preis': float(max_preis),
                    'diff': float(diff),
                    'diff_pct': float(diff_pct)
                })

    # Sortiere nach Preisänderung
    produkte_mit_aenderungen.sort(key=lambda x: x['diff_pct'], reverse=True)

    # === Preisentwicklung pro Produkt (statt Durchschnitt) ===
    preis_historie_produkte = []

    for produkt in produkte_queryset:
        # Nur Produkte mit mind. 2 Preiseinträgen
        if produkt.preishistorie.count() >= 2:
            # Hole Preishistorie für dieses spezifische Produkt
            historie = list(produkt.preishistorie.values('datum', 'preis').order_by('datum'))

            # Konvertiere Decimal zu Float für JavaScript
            historie_converted = [
                {
                    'datum': h['datum'].isoformat(),  # Konvertiere Datum zu String
                    'preis': float(h['preis']) if h['preis'] else 0.0
                }
                for h in historie
            ]

            preis_historie_produkte.append({
                'produkt_id': produkt.id,
                'produkt_name': produkt.name_normalisiert,
                'historie': historie_converted
            })

    # === Statistiken ===
    stats = produkte_queryset.aggregate(
        gesamt_produkte=Count('id'),
        gesamt_kaeufe=Sum('anzahl_kaeufe'),
        durchschnittspreis=Avg('durchschnittspreis')
    )

    context = {
        'produktgruppe': produktgruppe,
        'ueberkategorie': ueberkategorie,
        'produkte': produkte_mit_aenderungen,  # ✅ Jetzt JSON-serialisierbar
        'preis_historie_produkte': preis_historie_produkte,
        'stats': stats
    }

    return render(request, 'finance/_OLD_billa_preisentwicklung_produktgruppe.html', context)
"""


# ============================================================================
# PREISENTWICKLUNG - EINZELNES PRODUKT
# ❌ DEPRECATED
# ============================================================================
"""
@login_required
def billa_preisentwicklung_produkt(request, produkt_id):

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

    return render(request, 'finance/_OLD_billa_preisentwicklung_produkt.html', context)
"""

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

    return render(request, 'finance/billa_marken_liste.html', context)


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

    return render(request, 'finance/billa_marke_detail.html', context)


# ============================================================================
# MARKEN - PREISENTWICKLUNG
# ❌ DEPRECATED - Funktionalität jetzt in billa_marke_detail integriert
# ============================================================================

"""
@login_required
def billa_preisentwicklung_marke(request, marke):

    # Prüfe ob Marke existiert
    produkte_queryset = BillaProdukt.objects.filter(marke=marke)

    if not produkte_queryset.exists():
        from django.http import Http404
        raise Http404("Marke nicht gefunden")

    # === Berechne Preisänderungen für jedes Produkt ===
    produkte_mit_aenderungen = []

    for produkt in produkte_queryset.prefetch_related('preishistorie'):
        preis_stats = produkt.preishistorie.aggregate(
            min_preis=Min('preis'),
            max_preis=Max('preis'),
            count=Count('id')
        )

        if preis_stats['count'] >= 2 and preis_stats['min_preis']:
            min_preis = preis_stats['min_preis']
            max_preis = preis_stats['max_preis']
            diff = max_preis - min_preis

            if min_preis > 0:
                diff_pct = (diff / min_preis * 100)
                produkte_mit_aenderungen.append({
                    'produkt': produkt,
                    'min_preis': float(min_preis),
                    'max_preis': float(max_preis),
                    'diff': float(diff),
                    'diff_pct': float(diff_pct),
                    'produktgruppe': produkt.produktgruppe,
                    'ueberkategorie': produkt.ueberkategorie
                })

    # Sortiere nach Preisänderung
    produkte_mit_aenderungen.sort(key=lambda x: x['diff_pct'], reverse=True)

    # === Preisentwicklung der gesamten Marke (Durchschnitt) ===
    preis_historie_marke = BillaPreisHistorie.objects.filter(
        produkt__marke=marke
    ).values('datum').annotate(
        durchschnitt=Avg('preis'),
        min_preis=Min('preis'),
        max_preis=Max('preis')
    ).order_by('datum')

    # Konvertiere zu Liste mit Float-Werten
    preis_historie_converted = []
    for eintrag in preis_historie_marke:
        preis_historie_converted.append({
            'datum': eintrag['datum'].isoformat(),
            'durchschnitt': float(eintrag['durchschnitt']) if eintrag['durchschnitt'] else 0.0,
            'min_preis': float(eintrag['min_preis']) if eintrag['min_preis'] else 0.0,
            'max_preis': float(eintrag['max_preis']) if eintrag['max_preis'] else 0.0
        })

    # === Statistiken ===
    stats = produkte_queryset.aggregate(
        gesamt_produkte=Count('id'),
        gesamt_kaeufe=Sum('anzahl_kaeufe'),
        durchschnittspreis=Avg('durchschnittspreis')
    )

    context = {
        'marke': marke,
        'produkte': produkte_mit_aenderungen,
        'preis_historie_marke': preis_historie_converted,
        'stats': stats
    }

    return render(request, 'finance/_OLD_billa_preisentwicklung_marke.html', context)
"""


class BillaReceiptParser:
    """Parser für Billa-Rechnungen (aus dem Command kopiert)"""

    def __init__(self):
        self.artikel_pattern = re.compile(r'^(.+?)\s+([ABCDG])\s+([\d.,-]+)\s*$')
        self.gewicht_pattern = re.compile(r'^\s*([\d.]+)\s*kg\s*(?:\(N\))?\s*x\s*([\d.]+)\s*EUR/kg\s*$')
        self.menge_pattern = re.compile(r'^\s*(\d+)\s*x\s*([\d.]+)\s*$')
        self.rabatt_pattern = re.compile(
            r'^(NIMM MEHR|EXTREM AKTION|GRATIS AKTION|AKTIONSNACHLASS|'
            r'FILIALAKTION|Preiskorrektur|Jö Äpp Extrem Bon)\s+([ABCDG])?\s*([\d.,-]+)\s*$'
        )

    def parse_pdf(self, pdf_path):
        """Parst eine PDF-Rechnung"""
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() + "\n"

        lines = text.split('\n')

        data = {
            'datum': None,
            'zeit': None,
            'filiale': None,
            'kassa': None,
            'bon_nr': None,
            're_nr': None,
            'gesamt_preis': None,
            'gesamt_ersparnis': Decimal('0'),
            'zwischensumme': None,
            'mwst_b': None,
            'mwst_c': None,
            'mwst_g': None,
            'mwst_d': None,
            'oe_punkte_gesammelt': 0,
            'oe_punkte_eingeloest': 0,
            'pdf_datei': pdf_path,
            'artikel': []
        }

        data.update(self._extract_header(lines))
        data['artikel'] = self._extract_artikel(lines)

        return data

    def _extract_header(self, lines):
        """Extrahiert Header-Informationen"""
        info = {}

        for line in lines:
            # Datum und Zeit
            m = re.search(r'Datum:\s*(\d{2}\.\d{2}\.\d{4})\s+Zeit:\s*(\d{2}:\d{2})', line)
            if m:
                info['datum'] = datetime.strptime(m.group(1), '%d.%m.%Y').date()
                info['zeit'] = datetime.strptime(m.group(2), '%H:%M').time()

            # Filiale
            m = re.search(r'Filiale:\s*(\d+)', line)
            if m:
                info['filiale'] = m.group(1)

            # Kassa
            m = re.search(r'Kassa:\s*(\d+)', line)
            if m:
                info['kassa'] = int(m.group(1))

            # Bon-Nr
            m = re.search(r'Bon-Nr:\s*(\d+)', line)
            if m:
                info['bon_nr'] = m.group(1)

            # Re-Nr
            m = re.search(r'Re-Nr:\s*([\d-]+)', line)
            if m:
                info['re_nr'] = m.group(1)

            # Ersparnis
            m = re.search(r'HEUTE GESPART\s+([\d.,]+)\s*EUR', line)
            if m:
                info['gesamt_ersparnis'] = Decimal(m.group(1).replace(',', '.'))

            # Summe
            if line.startswith('Summe') and 'EUR' in line:
                m = re.search(r'([\d.,]+)$', line)
                if m:
                    info['gesamt_preis'] = Decimal(m.group(1).replace(',', '.'))

            # MwSt
            m = re.search(r'B:\s*10%\s*MwSt.*?=\s*([\d.,]+)', line)
            if m:
                info['mwst_b'] = Decimal(m.group(1).replace(',', '.'))

            m = re.search(r'C:\s*20%\s*MwSt.*?=\s*([\d.,]+)', line)
            if m:
                info['mwst_c'] = Decimal(m.group(1).replace(',', '.'))

            m = re.search(r'G:\s*13%\s*MwSt.*?=\s*([\d.,]+)', line)
            if m:
                info['mwst_g'] = Decimal(m.group(1).replace(',', '.'))

            # Ö-Punkte
            m = re.search(r'GESAMMELT\s+(\d+)', line)
            if m:
                info['oe_punkte_gesammelt'] = int(m.group(1))

            m = re.search(r'EINGELÖST\s+(\d+)', line)
            if m:
                info['oe_punkte_eingeloest'] = int(m.group(1))

        return info

    def _extract_artikel(self, lines):
        """Extrahiert Artikel aus den Zeilen"""
        artikel_liste = []
        position = 0
        pending_artikel = None

        for i, line in enumerate(lines):
            if pending_artikel and self._ist_gewicht_zeile(line):
                gewicht_data = self._parse_gewicht_zeile(line)
                pending_artikel.update(gewicht_data)
                artikel_liste.append(pending_artikel)
                pending_artikel = None
                continue

            if pending_artikel and self._ist_menge_zeile(line):
                menge_data = self._parse_menge_zeile(line)
                pending_artikel.update(menge_data)
                artikel_liste.append(pending_artikel)
                pending_artikel = None
                continue

            if pending_artikel:
                artikel_liste.append(pending_artikel)
                pending_artikel = None

            if self._ist_rabatt_zeile(line):
                rabatt_data = self._check_rabatt(line)
                if rabatt_data and artikel_liste:
                    artikel_liste[-1]['rabatt'] = rabatt_data['rabatt']
                    artikel_liste[-1]['rabatt_typ'] = rabatt_data['rabatt_typ']
                continue

            match = self.artikel_pattern.match(line.strip())
            if match:
                position += 1
                name = match.group(1).strip()
                preis = Decimal(match.group(3).replace(',', '.'))

                pending_artikel = {
                    'position': position,
                    'produkt_name': name,
                    'produkt_name_normalisiert': self._normalize_name(name),
                    'menge': Decimal('1'),
                    'einheit': 'Stk',
                    'einzelpreis': preis,
                    'gesamtpreis': preis,
                    'rabatt': Decimal('0'),
                    'rabatt_typ': None,
                    'mwst_kategorie': match.group(2),
                    'ist_gewichtsartikel': False,
                    'ist_mehrfachgebinde': name.startswith('@')
                }

        if pending_artikel:
            artikel_liste.append(pending_artikel)

        return artikel_liste

    def _ist_gewicht_zeile(self, line):
        return bool(self.gewicht_pattern.match(line.strip()))

    def _ist_menge_zeile(self, line):
        return bool(self.menge_pattern.match(line.strip()))

    def _parse_gewicht_zeile(self, line):
        match = self.gewicht_pattern.match(line.strip())
        if match:
            return {
                'menge': Decimal(match.group(1)),
                'einheit': 'kg',
                'einzelpreis': Decimal(match.group(2).replace(',', '.')),
                'ist_gewichtsartikel': True
            }
        return {}

    def _parse_menge_zeile(self, line):
        match = self.menge_pattern.match(line.strip())
        if match:
            return {
                'menge': Decimal(match.group(1)),
                'einzelpreis': Decimal(match.group(2).replace(',', '.'))
            }
        return {}

    def _ist_rabatt_zeile(self, line):
        line_stripped = line.strip()
        if re.match(r'^[A-Za-zäöüÄÖÜ\s]+-?\d+%\s+([ABCDG])?\s*-?[\d.,-]+\s*$', line_stripped):
            return True
        if self.rabatt_pattern.match(line_stripped):
            return True
        return False

    def _check_rabatt(self, line):
        line_stripped = line.strip()

        prozent_match = re.match(r'^(.+?)\s+(-?\d+)%\s+([ABCDG])?\s*([\d.,-]+)\s*', line_stripped)
        if prozent_match:
            rabatt_name = prozent_match.group(1).strip()
            prozent = prozent_match.group(2)
            betrag = prozent_match.group(4).replace(',', '.')
            return {
                'rabatt_typ': f'{rabatt_name} {prozent}%',
                'rabatt': abs(Decimal(betrag))
            }

        match = self.rabatt_pattern.match(line_stripped)
        if match:
            betrag = match.group(3).replace(',', '.')
            return {
                'rabatt_typ': match.group(1),
                'rabatt': abs(Decimal(betrag))
            }

        return None

    def _normalize_name(self, name):
        return name.lstrip('@').strip().lower()


@login_required
def billa_import_upload(request):
    """Upload-Formular für Billa-Rechnungen"""

    if request.method == 'POST' and request.FILES.getlist('pdf_files'):
        pdf_files = request.FILES.getlist('pdf_files')
        # WICHTIG: Checkbox gibt 'on' zurück wenn aktiviert, sonst existiert der Key nicht
        force = bool(request.POST.get('force'))

        stats = {
            'total': len(pdf_files),
            'imported': 0,
            'skipped': 0,
            'errors': 0,
            'error_details': []
        }

        parser = BillaReceiptParser()

        for pdf_file in pdf_files:
            # Speichere Datei temporär
            temp_dir = tempfile.mkdtemp()
            temp_path = os.path.join(temp_dir, pdf_file.name)

            try:
                # Schreibe Datei
                with open(temp_path, 'wb+') as destination:
                    for chunk in pdf_file.chunks():
                        destination.write(chunk)

                # Parse PDF (verwendet jetzt die konsolidierte Logik)
                data = parser.parse_pdf(temp_path)

                # Prüfe ob bereits importiert (VOR der Transaktion!)
                if not force and data.get('re_nr'):
                    if BillaEinkauf.objects.filter(re_nr=data['re_nr']).exists():
                        stats['skipped'] += 1
                        stats['error_details'].append({
                            'file': pdf_file.name,
                            'error': f'Rechnung bereits vorhanden (Re-Nr: {data["re_nr"]}). Aktiviere "Erneut importieren" um zu überschreiben.'
                        })
                        continue

                # Jedes PDF in eigener Transaktion!
                with transaction.atomic():
                    # Bei force: Alte Rechnung löschen
                    if force and data.get('re_nr'):
                        BillaEinkauf.objects.filter(re_nr=data['re_nr']).delete()

                    # Erstelle Einkauf und Artikel
                    _create_einkauf_with_artikel(data)

                stats['imported'] += 1

            except Exception as e:
                stats['errors'] += 1
                error_msg = str(e)

                # Debug-Info bei Parsing-Fehlern
                if "konnte nicht" in error_msg or "NULL" in error_msg:
                    try:
                        import pdfplumber
                        with pdfplumber.open(temp_path) as pdf:
                            first_page_text = pdf.pages[0].extract_text()
                            preview = first_page_text[:500] if first_page_text else "Kein Text extrahierbar"
                            error_msg += f"\n\nPDF-Vorschau (erste 500 Zeichen):\n{preview}"
                    except:
                        pass

                stats['error_details'].append({
                    'file': pdf_file.name,
                    'error': error_msg
                })

            finally:
                # Lösche temporäre Datei
                try:
                    os.remove(temp_path)
                    os.rmdir(temp_dir)
                except:
                    pass

        # Feedback-Nachrichten
        if stats['imported'] > 0:
            messages.success(request, f"✓ {stats['imported']} Rechnung(en) erfolgreich importiert")

        if stats['skipped'] > 0:
            messages.warning(request, f"⊘ {stats['skipped']} Rechnung(en) übersprungen (bereits vorhanden)")
            # Zeige Details für übersprungene Rechnungen
            for error in [e for e in stats['error_details'] if 'bereits vorhanden' in e.get('error', '')]:
                messages.info(request, f"  • {error['file']}")

        if stats['errors'] > 0:
            messages.error(request, f"✗ {stats['errors']} Fehler beim Import")
            # Zeige nur echte Fehler (nicht die Duplikate)
            for error in [e for e in stats['error_details'] if 'bereits vorhanden' not in e.get('error', '')]:
                messages.error(request, f"  • {error['file']}: {error['error']}")

        return redirect('finance:billa_dashboard')

    context = {}
    return render(request, 'finance/billa_import.html', context)


def _create_einkauf_with_artikel(data):
    """
    Gemeinsame Logik für Einkauf-Erstellung.
    Wird von View und Command verwendet.

    WICHTIG: Wandelt filiale von String → ForeignKey-Objekt um!
    """
    # Erstelle/finde Filiale
    filial_nr = data.pop('filiale', None)
    if not filial_nr:
        raise ValueError("Keine Filial-Nummer gefunden")

    filiale_obj, created = BillaFiliale.objects.get_or_create(
        filial_nr=filial_nr,
        defaults={
            'name': f'Filiale {filial_nr}',  # Fallback-Name
            'typ': 'billa',  # Default-Typ
            'aktiv': True
        }
    )

    if created:
        print(f"ℹ️  Neue Filiale {filial_nr} automatisch erstellt")

    # Erstelle Einkauf
    artikel_liste = data.pop('artikel')
    data['filiale'] = filiale_obj  # ForeignKey-Objekt statt String!
    einkauf = BillaEinkauf.objects.create(**data)

    # Erstelle Artikel
    for artikel_data in artikel_liste:
        artikel_data['einkauf'] = einkauf

        produkt_name_norm = artikel_data['produkt_name_normalisiert']
        produkt_name_original = artikel_data['produkt_name']

        # Finde oder erstelle Produkt
        produkt, created = BillaProdukt.objects.get_or_create(
            name_normalisiert=produkt_name_norm,
            defaults={
                'name_original': produkt_name_original,
                'letzter_preis': artikel_data['gesamtpreis'],
                'marke': BrandMapper.extract_brand(produkt_name_original)
            }
        )

        # Aktualisiere Marke falls noch nicht gesetzt
        if not created and not produkt.marke:
            produkt.marke = BrandMapper.extract_brand(produkt_name_original)
            produkt.save(update_fields=['marke'])

        # Aktualisiere Original-Namen (kürzeste Variante bevorzugen)
        if not created:
            if len(produkt_name_original) < len(produkt.name_original):
                produkt.name_original = produkt_name_original
                produkt.save(update_fields=['name_original'])

        artikel_data['produkt'] = produkt
        artikel = BillaArtikel.objects.create(**artikel_data)

        # Erstelle Preishistorie (filiale ist jetzt ein ForeignKey-Objekt!)
        BillaPreisHistorie.objects.create(
            produkt=produkt,
            artikel=artikel,
            datum=einkauf.datum,
            preis=artikel.preis_pro_einheit,
            menge=artikel.menge,
            einheit=artikel.einheit,
            filiale=einkauf.filiale  # Verwendet das Filiale-Objekt vom Einkauf
        )

        # Aktualisiere Produkt-Statistiken
        produkt.update_statistiken()

    return einkauf

# Füge diese View in finance/views_billa.py hinzu, direkt VOR der billa_einkauf_detail View:

@login_required
def billa_einkauefe_uebersicht(request):
    """Übersicht aller Einkäufe"""

    # Filter aus GET-Parametern
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    filiale_id = request.GET.get('filiale')

    # Basis-Queryset
    einkaufe = BillaEinkauf.objects.select_related('filiale')

    # Datum-Filter
    if start_date:
        einkaufe = einkaufe.filter(datum__gte=start_date)
    if end_date:
        einkaufe = einkaufe.filter(datum__lte=end_date)

    # Filialen-Filter
    if filiale_id and filiale_id != 'alle':
        einkaufe = einkaufe.filter(filiale__filial_nr=filiale_id)

    # Sortierung
    einkaufe = einkaufe.order_by('-datum', '-zeit')

    # Statistiken
    stats = einkaufe.aggregate(
        anzahl=Count('id'),
        gesamt_ausgaben=Sum('gesamt_preis'),
        gesamt_ersparnis=Sum('gesamt_ersparnis'),
        avg_warenkorb=Avg('gesamt_preis')
    )

    # Filialen für Filter
    filialen = BillaFiliale.objects.filter(aktiv=True).order_by('filial_nr')

    context = {
        'einkaufe': einkaufe,
        'stats': stats,
        'filialen': filialen,
        'selected_filiale': filiale_id or 'alle',
        'start_date': start_date,
        'end_date': end_date,
    }

    return render(request, 'finance/billa_einkauefe_uebersicht.html', context)

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

    return render(request, 'finance/billa_ueberkategorie_detail.html', context)