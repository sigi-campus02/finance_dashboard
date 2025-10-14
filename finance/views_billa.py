# finance/views_billa.py

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
    BillaPreisHistorie
)
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

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

    # Preisentwicklung
    preis_historie = produkt.preishistorie.order_by('datum')

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
        'preis_historie': preis_historie,
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