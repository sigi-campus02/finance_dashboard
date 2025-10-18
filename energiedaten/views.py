# views.py
from django.shortcuts import render
from django.db.models import Sum, Avg, Max, Min, Count
from django.db.models.functions import (
    TruncMonth,
    ExtractWeek,
    ExtractYear,
)
from datetime import datetime, timedelta
from .models import Stromverbrauch


def energiedaten_dashboard(request):
    """Dashboard mit Übersicht und Statistiken zum Stromverbrauch"""

    # Zeitraum-Filter aus GET-Parameter
    zeitraum = request.GET.get('zeitraum', '30')  # Standard: 30 Tage

    if zeitraum == 'alle':
        daten = Stromverbrauch.objects.all()
        titel = "Alle Daten"
    else:
        tage = int(zeitraum)
        datum_von = datetime.now().date() - timedelta(days=tage)
        daten = Stromverbrauch.objects.filter(datum__gte=datum_von)
        titel = f"Letzte {tage} Tage"

    # Gesamtstatistiken
    stats = daten.aggregate(
        gesamt=Sum('verbrauch_kwh'),
        durchschnitt=Avg('verbrauch_kwh'),
        maximum=Max('verbrauch_kwh'),
        minimum=Min('verbrauch_kwh'),
        anzahl_tage=Count('id')
    )

    # Monatliche Aggregation
    monatlich = daten.annotate(
        monat=TruncMonth('datum')
    ).values('monat').annotate(
        verbrauch=Sum('verbrauch_kwh'),
        durchschnitt=Avg('verbrauch_kwh'),
        tage=Count('id')
    ).order_by('-monat')[:12]

    # Wöchentliche Aggregation für Chart (Kalenderwochen nach Jahr)
    woechentlich = daten.annotate(
        jahr=ExtractYear('datum'),
        kw=ExtractWeek('datum')
    ).values('jahr', 'kw').annotate(
        verbrauch=Sum('verbrauch_kwh')
    ).order_by('jahr', 'kw')

    # Verbrauch nach Wochentag
    wochentage = []
    wochentag_namen = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']

    for tag_nr in range(1, 8):
        tag_daten = [d for d in daten if d.wochentag == tag_nr]
        if tag_daten:
            durchschnitt = sum(d.verbrauch_kwh for d in tag_daten) / len(tag_daten)
            wochentage.append({
                'tag': wochentag_namen[tag_nr - 1],
                'durchschnitt': round(durchschnitt, 2),
                'anzahl': len(tag_daten)
            })

    # Aktuelle Daten für Tabelle (letzte 30 Einträge)
    aktuelle_daten = daten.order_by('-datum')[:30]

    # Daten für Charts vorbereiten
    kw_labels = sorted({eintrag['kw'] for eintrag in woechentlich})
    jahre = sorted({eintrag['jahr'] for eintrag in woechentlich})

    chart_labels = [f"KW {kw:02d}" for kw in kw_labels]

    farben = [
        '#0d6efd',  # Blau
        '#20c997',  # Grün
        '#ffc107',  # Gelb
        '#dc3545',  # Rot
        '#6f42c1',  # Lila
        '#198754',  # Dunkelgrün
        '#fd7e14',  # Orange
    ]

    jahreswerte = {}
    for eintrag in woechentlich:
        jahr = eintrag['jahr']
        kw = eintrag['kw']
        jahreswerte.setdefault(jahr, {})[kw] = float(eintrag['verbrauch'])

    chart_datasets = []
    for index, jahr in enumerate(jahre):
        farbe = farben[index % len(farben)]
        werte = []
        for kw in kw_labels:
            wert = jahreswerte[jahr].get(kw)
            werte.append(round(wert, 2) if wert is not None else None)

        chart_datasets.append({
            'label': str(jahr),
            'data': werte,
            'borderColor': farbe,
            'backgroundColor': farbe,
            'tension': 0.35,
            'fill': False,
            'pointRadius': 3,
            'pointBackgroundColor': '#ffffff',
            'pointBorderColor': farbe,
            'pointHoverRadius': 5,
        })

    context = {
        'titel': titel,
        'zeitraum': zeitraum,
        'stats': stats,
        'monatlich': monatlich,
        'wochentage': wochentage,
        'aktuelle_daten': aktuelle_daten,
        'chart_labels': chart_labels,
        'chart_datasets': chart_datasets,
    }

    return render(request, 'energiedaten/dashboard.html', context)


def energiedaten_detail(request):
    """Detaillierte Tabellenansicht aller Daten"""

    # Sortierung
    sortierung = request.GET.get('sort', '-datum')

    # Alle Daten mit Sortierung
    daten = Stromverbrauch.objects.all().order_by(sortierung)

    # Pagination könnte hier hinzugefügt werden

    context = {
        'daten': daten,
        'sortierung': sortierung,
    }

    return render(request, 'energiedaten/detail.html', context)