import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Avg, Q
from django.db.models.functions import TruncDate, TruncMonth
from django.http import JsonResponse
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
        'produkt__ueberkategorie',
        'produkt__produktgruppe'
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

    # Ausgaben im Zeitverlauf (täglich)
    daily_spending_raw = einkaufe.annotate(
        tag=TruncDate('datum')
    ).values('tag').annotate(
        ausgaben=Sum('gesamt_preis')
    ).order_by('tag')

    daily_spending = [
        {
            'tag': item['tag'].strftime('%Y-%m-%d'),
            'ausgaben': float(item['ausgaben']) if item['ausgaben'] else 0
        }
        for item in daily_spending_raw
    ]

    # Monatliche Ausgaben nach Überkategorie
    monthly_by_group_raw = artikel.annotate(
        monat=TruncMonth('einkauf__datum')
    ).values('monat', 'produkt__ueberkategorie__name').annotate(
        ausgaben=Sum('gesamtpreis')
    ).order_by('monat', 'produkt__ueberkategorie__name')

    monthly_data = {}
    all_ueberkategorien = set()

    for item in monthly_by_group_raw:
        monat_str = item['monat'].strftime('%Y-%m') if item['monat'] else 'Unbekannt'
        ueberkategorie = item['produkt__ueberkategorie__name'] or 'Ohne Kategorie'
        ausgaben = float(item['ausgaben']) if item['ausgaben'] else 0

        if monat_str not in monthly_data:
            monthly_data[monat_str] = {}

        monthly_data[monat_str][ueberkategorie] = ausgaben
        all_ueberkategorien.add(ueberkategorie)

    kategorie_totals = {}
    for kat in all_ueberkategorien:
        kategorie_totals[kat] = sum(
            monthly_data.get(m, {}).get(kat, 0)
            for m in monthly_data.keys()
        )

    ueberkategorien_sorted = sorted(
        all_ueberkategorien,
        key=lambda kat: kategorie_totals[kat],
        reverse=True
    )

    gesamt_ausgaben = sum(kategorie_totals.values())
    kumulativ = 0
    top_kategorien = []

    for kat in ueberkategorien_sorted:
        kumulativ += kategorie_totals[kat]
        top_kategorien.append(kat)
        if kumulativ >= gesamt_ausgaben * 0.80 or len(top_kategorien) >= 8:
            break

    sonstige_kategorien = [k for k in ueberkategorien_sorted if k not in top_kategorien]

    alle_monate = sorted(monthly_data.keys())
    kategorien_for_chart = top_kategorien.copy()

    if sonstige_kategorien:
        kategorien_for_chart.append('Sonstiges')

    monthly_spending_stacked = {
        'monate': alle_monate,
        'kategorien': kategorien_for_chart,
        'daten': {}
    }

    for kat in top_kategorien:
        monthly_spending_stacked['daten'][kat] = [
            monthly_data.get(monat, {}).get(kat, 0)
            for monat in alle_monate
        ]

    if sonstige_kategorien:
        monthly_spending_stacked['daten']['Sonstiges'] = [
            sum(monthly_data.get(monat, {}).get(kat, 0) for kat in sonstige_kategorien)
            for monat in alle_monate
        ]

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

    top_produkte_anzahl_raw = artikel.values(
        'produkt__name_korrigiert',
        'produkt__ueberkategorie__name'
    ).annotate(
        anzahl=Count('id'),
        ausgaben=Sum('gesamtpreis')
    ).order_by('-anzahl')[:15]

    top_produkte_anzahl = [
        {
            'produkt__name_korrigiert': item['produkt__name_korrigiert'],
            'produkt__ueberkategorie': item['produkt__ueberkategorie__name'],
            'anzahl': item['anzahl'],
            'ausgaben': float(item['ausgaben']) if item['ausgaben'] else 0
        }
        for item in top_produkte_anzahl_raw
    ]

    top_produkte_ausgaben_raw = artikel.values(
        'produkt__name_korrigiert',
        'produkt__ueberkategorie__name'
    ).annotate(
        ausgaben=Sum('gesamtpreis'),
        anzahl=Count('id')
    ).order_by('-ausgaben')[:15]

    top_produkte_ausgaben = [
        {
            'produkt__name_korrigiert': item['produkt__name_korrigiert'],
            'produkt__ueberkategorie': item['produkt__ueberkategorie__name'],
            'ausgaben': float(item['ausgaben']) if item['ausgaben'] else 0,
            'anzahl': item['anzahl']
        }
        for item in top_produkte_ausgaben_raw
    ]

    # Ausgaben nach Kategorie (Überkategorien)
    ausgaben_kategorie_raw = artikel.values(
        'produkt__ueberkategorie__name'
    ).annotate(
        ausgaben=Sum('gesamtpreis')
    ).order_by('-ausgaben')

    ausgaben_kategorie = [
        {
            'produkt__ueberkategorie': item['produkt__ueberkategorie__name'] or 'Ohne Kategorie',
            'ausgaben': float(item['ausgaben']) if item['ausgaben'] else 0
        }
        for item in ausgaben_kategorie_raw
    ]

    # ========================================
    # ✅ NEU: Produktgruppen nach Überkategorie für Drill-Down
    # ========================================
    produktgruppen_nach_kategorie = {}

    # Hole alle Überkategorien mit Ausgaben
    ueberkategorien_mit_ausgaben = artikel.values(
        'produkt__ueberkategorie__name'
    ).annotate(
        ausgaben=Sum('gesamtpreis')
    ).order_by('-ausgaben')

    for ueberkategorie_item in ueberkategorien_mit_ausgaben:
        ueberkategorie_name = ueberkategorie_item['produkt__ueberkategorie__name']
        if not ueberkategorie_name:
            ueberkategorie_name = 'Ohne Kategorie'

        # Aggregiere Produktgruppen für diese Überkategorie
        if ueberkategorie_name == 'Ohne Kategorie':
            produktgruppen = artikel.filter(
                produkt__ueberkategorie__isnull=True
            ).values(
                'produkt__produktgruppe__name'
            ).annotate(
                ausgaben=Sum('gesamtpreis'),
                anzahl_kaeufe=Count('id')
            ).order_by('-ausgaben')
        else:
            produktgruppen = artikel.filter(
                produkt__ueberkategorie__name=ueberkategorie_name
            ).values(
                'produkt__produktgruppe__name'
            ).annotate(
                ausgaben=Sum('gesamtpreis'),
                anzahl_kaeufe=Count('id')
            ).order_by('-ausgaben')

    # Rabatte nach Typ
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


@login_required
def billa_dashboard_produktgruppen_ajax(request):
    """API Endpoint für Produktgruppen einer Überkategorie"""
    ueberkategorie = request.GET.get('ueberkategorie')

    if not ueberkategorie:
        return JsonResponse({'error': 'Keine Überkategorie angegeben'}, status=400)

    # Filter aus GET-Parametern (für Konsistenz mit Dashboard)
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    filiale_id = request.GET.get('filiale')

    # Basis-Queryset
    artikel = BillaArtikel.objects.select_related(
        'produkt__ueberkategorie',
        'produkt__produktgruppe'
    )

    # Datum-Filter
    if start_date:
        artikel = artikel.filter(einkauf__datum__gte=start_date)
    if end_date:
        artikel = artikel.filter(einkauf__datum__lte=end_date)

    # Filialen-Filter
    if filiale_id and filiale_id != 'alle':
        artikel = artikel.filter(einkauf__filiale__filial_nr=filiale_id)

    # Aggregiere Produktgruppen für diese Überkategorie
    if ueberkategorie == 'Ohne Kategorie':
        produktgruppen = artikel.filter(
            produkt__ueberkategorie__isnull=True
        ).values(
            'produkt__produktgruppe__name'
        ).annotate(
            ausgaben=Sum('gesamtpreis'),
            anzahl_kaeufe=Count('id')
        ).order_by('-ausgaben')
    else:
        produktgruppen = artikel.filter(
            produkt__ueberkategorie__name=ueberkategorie
        ).values(
            'produkt__produktgruppe__name'
        ).annotate(
            ausgaben=Sum('gesamtpreis'),
            anzahl_kaeufe=Count('id')
        ).order_by('-ausgaben')

    # Konvertiere zu JSON
    data = [
        {
            'name': pg['produkt__produktgruppe__name'] or 'Ohne Gruppe',
            'ausgaben': float(pg['ausgaben']) if pg['ausgaben'] else 0,
            'anzahl_kaeufe': pg['anzahl_kaeufe']
        }
        for pg in produktgruppen if pg['ausgaben'] and pg['ausgaben'] > 0
    ]

    return JsonResponse({
        'ueberkategorie': ueberkategorie,
        'produktgruppen': data
    })



@login_required
def billa_dashboard_produkte_ajax(request):
    """API Endpoint für Produkte einer Produktgruppe"""
    produktgruppe = request.GET.get('produktgruppe')
    ueberkategorie = request.GET.get('ueberkategorie')  # Optional für Fallback

    if not produktgruppe:
        return JsonResponse({'error': 'Keine Produktgruppe angegeben'}, status=400)

    # Filter aus GET-Parametern
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    filiale_id = request.GET.get('filiale')

    # Basis-Queryset
    artikel = BillaArtikel.objects.select_related(
        'produkt__ueberkategorie',
        'produkt__produktgruppe'
    )

    # Datum-Filter
    if start_date:
        artikel = artikel.filter(einkauf__datum__gte=start_date)
    if end_date:
        artikel = artikel.filter(einkauf__datum__lte=end_date)

    # Filialen-Filter
    if filiale_id and filiale_id != 'alle':
        artikel = artikel.filter(einkauf__filiale__filial_nr=filiale_id)

    # Aggregiere Produkte für diese Produktgruppe
    if produktgruppe == 'Ohne Gruppe':
        produkte = artikel.filter(
            produkt__produktgruppe__isnull=True
        ).values(
            'produkt__name_korrigiert',
            'produkt__id'
        ).annotate(
            ausgaben=Sum('gesamtpreis'),
            anzahl_kaeufe=Count('id')
        ).order_by('-ausgaben')[:20]  # Limit auf Top 20
    else:
        produkte = artikel.filter(
            produkt__produktgruppe__name=produktgruppe
        ).values(
            'produkt__name_korrigiert',
            'produkt__id'
        ).annotate(
            ausgaben=Sum('gesamtpreis'),
            anzahl_kaeufe=Count('id')
        ).order_by('-ausgaben')[:20]  # Limit auf Top 20

    # Konvertiere zu JSON
    data = [
        {
            'name': p['produkt__name_korrigiert'] or 'Unbekannt',
            'ausgaben': float(p['ausgaben']) if p['ausgaben'] else 0,
            'anzahl_kaeufe': p['anzahl_kaeufe'],
            'produkt_id': p['produkt__id']
        }
        for p in produkte if p['ausgaben'] and p['ausgaben'] > 0
    ]

    return JsonResponse({
        'produktgruppe': produktgruppe,
        'produkte': data
    })