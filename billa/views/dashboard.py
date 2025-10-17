import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Avg, Q
from django.db.models.functions import TruncDate, TruncMonth

from billa.models import (
    BillaEinkauf, BillaArtikel, BillaProdukt, BillaFiliale
)


@login_required
def billa_dashboard(request):
    """Haupt-Dashboard für Billa-Analysen"""

    # Filter aus GET-Parametern
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    filiale_id = request.GET.get('filiale')

    # Basis-Queryset
    einkaufe = BillaEinkauf.objects.select_related('filiale')
    artikel = BillaArtikel.objects.select_related(
        'einkauf__filiale',
        'produkt__ueberkategorie',  # ✅ NEU: select_related für Performance
        'produkt__produktgruppe'     # ✅ NEU: optional, falls später gebraucht
    )

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
    ).values('monat', 'produkt__ueberkategorie__name').annotate(  # ✅ GEÄNDERT: __name
        ausgaben=Sum('gesamtpreis')
    ).order_by('monat', 'produkt__ueberkategorie__name')  # ✅ GEÄNDERT: __name

    # Strukturiere Daten: {monat: {ueberkategorie: ausgaben}}
    monthly_data = {}
    all_ueberkategorien = set()

    for item in monthly_by_group_raw:
        monat_str = item['monat'].strftime('%Y-%m') if item['monat'] else 'Unbekannt'
        ueberkategorie = item['produkt__ueberkategorie__name'] or 'Ohne Kategorie'  # ✅ GEÄNDERT: __name
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
        reverse=True
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
        'produkt__name_korrigiert',
        'produkt__ueberkategorie__name'  # ✅ GEÄNDERT: __name
    ).annotate(
        anzahl=Count('id'),
        ausgaben=Sum('gesamtpreis')
    ).order_by('-anzahl')[:15]

    top_produkte_anzahl = [
        {
            'produkt__name_korrigiert': item['produkt__name_korrigiert'],
            'produkt__ueberkategorie': item['produkt__ueberkategorie__name'],  # ✅ GEÄNDERT: __name
            'anzahl': item['anzahl'],
            'ausgaben': float(item['ausgaben']) if item['ausgaben'] else 0
        }
        for item in top_produkte_anzahl_raw
    ]

    # Top Produkte nach Ausgaben - JSON-serialisierbar machen
    top_produkte_ausgaben_raw = artikel.values(
        'produkt__name_korrigiert',
        'produkt__ueberkategorie__name'  # ✅ GEÄNDERT: __name
    ).annotate(
        ausgaben=Sum('gesamtpreis'),
        anzahl=Count('id')
    ).order_by('-ausgaben')[:15]

    top_produkte_ausgaben = [
        {
            'produkt__name_korrigiert': item['produkt__name_korrigiert'],
            'produkt__ueberkategorie': item['produkt__ueberkategorie__name'],  # ✅ GEÄNDERT: __name
            'ausgaben': float(item['ausgaben']) if item['ausgaben'] else 0,
            'anzahl': item['anzahl']
        }
        for item in top_produkte_ausgaben_raw
    ]

    # Ausgaben nach Kategorie - JSON-serialisierbar machen
    ausgaben_kategorie_raw = artikel.values(
        'produkt__ueberkategorie__name'  # ✅ GEÄNDERT: __name
    ).annotate(
        ausgaben=Sum('gesamtpreis')
    ).order_by('-ausgaben')

    ausgaben_kategorie = [
        {
            'produkt__ueberkategorie': item['produkt__ueberkategorie__name'],  # ✅ GEÄNDERT: __name (Key bleibt gleich für Template-Kompatibilität)
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
        'monthly_spending': json.dumps(monthly_spending),
        'monthly_spending_stacked': json.dumps(monthly_spending_stacked),
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

    return render(request, 'billa/billa_dashboard.html', context)