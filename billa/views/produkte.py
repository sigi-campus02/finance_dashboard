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
    BillaArtikel, BillaProdukt, BillaPreisHistorie, BillaUeberkategorie, BillaProduktgruppe
)

logger = logging.getLogger(__name__)


@login_required
def billa_produkt_detail(request, produkt_id):
    """Detail-Ansicht eines Produkts - zeigt ALLE Varianten mit gleichem name_korrigiert"""

    hauptprodukt = get_object_or_404(BillaProdukt, pk=produkt_id)

    # Hole ALLE Produkte mit dem gleichen name_korrigiert
    alle_varianten = BillaProdukt.objects.filter(
        name_korrigiert=hauptprodukt.name_korrigiert
    ).select_related('ueberkategorie', 'produktgruppe').order_by('-anzahl_kaeufe')  # ✅ GEÄNDERT

    anzahl_varianten = alle_varianten.count()

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

    # Preisentwicklung
    preis_historie_raw = BillaPreisHistorie.objects.filter(
        produkt__name_korrigiert=hauptprodukt.name_korrigiert
    ).select_related('filiale', 'produkt').order_by('datum')  # ✅ GEÄNDERT

    preis_historie_json = []
    for h in preis_historie_raw:
        preis_historie_json.append({
            'datum': h.datum.strftime('%Y-%m-%d'),
            'preis': float(h.preis),
            'menge': float(h.menge),
            'filiale': h.filiale.name if h.filiale else 'Unbekannt',
            'produkt_id': h.produkt.id
        })

    # Letzte Käufe
    letzte_kaeufe = alle_artikel.select_related(
        'einkauf', 'produkt', 'produkt__ueberkategorie', 'produkt__produktgruppe'  # ✅ GEÄNDERT
    ).order_by('-einkauf__datum')[:30]

    # Statistiken pro Variante
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

    # Filialen-Verteilung
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
    """Liste aller Produkte - GRUPPIERT nach name_korrigiert"""

    # Filter
    ueberkategorie = request.GET.get('ueberkategorie')
    produktgruppe = request.GET.get('produktgruppe')
    suche = request.GET.get('suche')
    sortierung = request.GET.get('sort', '-anzahl_kaeufe')

    # GRUPPIERUNG nach name_korrigiert mit ForeignKey-Annotations
    produkte_grouped = BillaProdukt.objects.values(
        'name_korrigiert',
        'ueberkategorie__id',  # ✅ GEÄNDERT: __id statt direkter Wert
        'ueberkategorie__name',  # ✅ GEÄNDERT: __name für Anzeige
        'produktgruppe__id',  # ✅ GEÄNDERT
        'produktgruppe__name'  # ✅ GEÄNDERT
    ).annotate(
        anzahl_varianten=Count('id'),
        gesamt_kaeufe=Sum('anzahl_kaeufe'),
        durchschnittspreis=Avg('durchschnittspreis'),
        letzter_preis=Avg('letzter_preis'),
        erste_id=Min('id')
    )

    # Filter nach Überkategorie
    if ueberkategorie and ueberkategorie != 'alle':
        produkte_grouped = produkte_grouped.filter(ueberkategorie__id=ueberkategorie)  # ✅ GEÄNDERT

    # Filter nach Produktgruppe
    if produktgruppe and produktgruppe != 'alle':
        produkte_grouped = produkte_grouped.filter(produktgruppe__id=produktgruppe)  # ✅ GEÄNDERT

    # Suche
    if suche:
        produkte_grouped = produkte_grouped.filter(
            Q(name_korrigiert__icontains=suche)
        )

    # Sortierung bleibt gleich
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

    # Filter-Optionen - ✅ GEÄNDERT
    alle_ueberkategorien = BillaUeberkategorie.objects.all().order_by('name')
    alle_produktgruppen = BillaProduktgruppe.objects.all().order_by('name')

    # Produktgruppen-Mapping für JavaScript - ✅ GEÄNDERT
    produktgruppen_by_ueberkategorie = {}
    for ukat in alle_ueberkategorien:
        gruppen = ukat.produktgruppen.all().values('id', 'name')
        produktgruppen_by_ueberkategorie[str(ukat.id)] = [
            {'id': g['id'], 'name': g['name']} for g in gruppen
        ]

    context = {
        'produkte': produkte_grouped,
        'ueberkategorien': alle_ueberkategorien,
        'produktgruppen': alle_produktgruppen,
        'selected_ueberkategorie': ueberkategorie or 'alle',
        'selected_produktgruppe': produktgruppe or 'alle',
        'selected_kategorie_display': None,  # Wird im Template aufgelöst
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

    # GET: Anzeige der Mapper-Seite
    if request.method == 'GET':
        # Filter aus GET-Parametern
        suche = request.GET.get('suche', '')
        filter_typ = request.GET.get('filter', 'alle')
        ueberkategorie_filter = request.GET.get('ueberkategorie_filter', '')
        produktgruppe_filter = request.GET.get('produktgruppe_filter', '')

        # Basis-Queryset mit select_related für Performance
        produkte = BillaProdukt.objects.select_related(
            'ueberkategorie', 'produktgruppe'
        )

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

        # Überkategorie-Filter (jetzt mit ID!)
        if ueberkategorie_filter:
            produkte = produkte.filter(ueberkategorie__id=ueberkategorie_filter)

        # Produktgruppe-Filter (jetzt mit ID!)
        if produktgruppe_filter:
            produkte = produkte.filter(produktgruppe__id=produktgruppe_filter)

        # Pagination (100 Produkte pro Seite)
        from django.core.paginator import Paginator
        paginator = Paginator(produkte, 100)
        page_number = request.GET.get('page', 1)
        produkte_page = paginator.get_page(page_number)

        # Verfügbare Produktgruppen pro Produkt hinzufügen
        produkte_liste = []
        for produkt in produkte_page:
            # Verfügbare Produktgruppen für dieses Produkt
            if produkt.ueberkategorie:
                produkt.verfuegbare_gruppen = produkt.ueberkategorie.produktgruppen.all()
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

        # Lade alle Überkategorien und Produktgruppen
        ueberkategorien = BillaUeberkategorie.objects.all().order_by('name')

        # Produktgruppen gruppiert nach Überkategorie (für JavaScript)
        produktgruppen_map = {}
        for ueberkat in ueberkategorien:
            produktgruppen_map[str(ueberkat.id)] = [
                {'id': pg.id, 'name': pg.name}
                for pg in ueberkat.produktgruppen.all().order_by('name')
            ]

        context = {
            'produkte': produkte_liste,
            'page_obj': produkte_page,
            'stats': stats,
            'suche': suche,
            'filter': filter_typ,
            'ueberkategorie_filter': ueberkategorie_filter,
            'produktgruppe_filter': produktgruppe_filter,
            'ueberkategorien': ueberkategorien,
            'produktgruppen_json': json.dumps(produktgruppen_map),
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

                # Neue Werte aus POST (jetzt IDs statt Namen!)
                ueberkategorie_id = request.POST.get(f'ueberkategorie_{produkt_id}', '').strip()
                produktgruppe_id = request.POST.get(f'produktgruppe_{produkt_id}', '').strip()
                name_korrigiert = request.POST.get(f'name_korrigiert_{produkt_id}', '').strip()

                # Prüfe ob sich was geändert hat
                changed = False

                # Überkategorie
                if ueberkategorie_id:
                    try:
                        ueberkat_obj = BillaUeberkategorie.objects.get(id=ueberkategorie_id)
                        if produkt.ueberkategorie != ueberkat_obj:
                            produkt.ueberkategorie = ueberkat_obj
                            changed = True
                    except BillaUeberkategorie.DoesNotExist:
                        pass
                else:
                    if produkt.ueberkategorie is not None:
                        produkt.ueberkategorie = None
                        changed = True

                # Produktgruppe
                if produktgruppe_id:
                    try:
                        gruppe_obj = BillaProduktgruppe.objects.get(id=produktgruppe_id)
                        if produkt.produktgruppe != gruppe_obj:
                            produkt.produktgruppe = gruppe_obj
                            changed = True
                    except BillaProduktgruppe.DoesNotExist:
                        pass
                else:
                    if produkt.produktgruppe is not None:
                        produkt.produktgruppe = None
                        changed = True

                # Name korrigiert
                name_korrigiert = name_korrigiert if name_korrigiert else None
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

    KATEGORIE_ICONS = {
        'Gemüse': 'bi-basket',
        'Obst': 'bi-apple',
        # ... restliche Icons
    }

    # Filter
    ueberkategorie_filter = request.GET.get('ueberkategorie')
    suche = request.GET.get('suche')
    sortierung = request.GET.get('sort', '-anzahl_kaeufe')

    # ✅ GEÄNDERT: Aggregiere über Produktgruppen-Tabelle
    produktgruppen = BillaProduktgruppe.objects.select_related(
        'ueberkategorie'
    ).annotate(
        anzahl_produkte=Count('produkte'),
        anzahl_kaeufe=Sum('produkte__anzahl_kaeufe'),
        durchschnittspreis=Avg('produkte__durchschnittspreis'),
        aktueller_preis=Avg('produkte__letzter_preis')
    )

    # Filter nach Überkategorie
    if ueberkategorie_filter and ueberkategorie_filter != 'alle':
        produktgruppen = produktgruppen.filter(ueberkategorie__id=ueberkategorie_filter)  # ✅ GEÄNDERT

    # Suche
    if suche:
        produktgruppen = produktgruppen.filter(name__icontains=suche)

    # Sortierung
    sortierung_map = {
        '-anzahl_kaeufe': '-anzahl_kaeufe',
        'anzahl_kaeufe': 'anzahl_kaeufe',
        '-durchschnittspreis': '-durchschnittspreis',
        'durchschnittspreis': 'durchschnittspreis',
        'produktgruppe': 'name',  # ✅ GEÄNDERT
        '-produktgruppe': '-name',  # ✅ GEÄNDERT
        '-anzahl_produkte': '-anzahl_produkte'
    }
    produktgruppen = produktgruppen.order_by(sortierung_map.get(sortierung, '-anzahl_kaeufe'))

    # Liste mit Icons
    produktgruppen_list = []
    for gruppe in produktgruppen:
        produktgruppen_list.append({
            'id': gruppe.id,  # ✅ NEU
            'name': gruppe.name,
            'ueberkategorie': gruppe.ueberkategorie.name,
            'icon': KATEGORIE_ICONS.get(gruppe.ueberkategorie.name, 'bi-box-seam'),
            'anzahl_produkte': gruppe.anzahl_produkte,
            'anzahl_kaeufe': gruppe.anzahl_kaeufe or 0,
            'durchschnittspreis': gruppe.durchschnittspreis,
            'aktueller_preis': gruppe.aktueller_preis
        })

    # Alle Überkategorien für Filter
    alle_ueberkategorien = BillaUeberkategorie.objects.all().order_by('name')

    context = {
        'produktgruppen': produktgruppen_list,
        'ueberkategorien': alle_ueberkategorien,
        'selected_ueberkategorie': ueberkategorie_filter or 'alle',
        'suche': suche or '',
        'sortierung': sortierung,
        'gesamt_gruppen': len(produktgruppen_list)
    }

    return render(request, 'billa/billa_produktgruppen_liste.html', context)


@login_required
def billa_produktgruppe_detail(request, produktgruppe):
    """Detailansicht einer Produktgruppe"""

    # Hole Produktgruppe per ID
    try:
        produktgruppe_obj = BillaProduktgruppe.objects.get(id=produktgruppe_id)
    except BillaProduktgruppe.DoesNotExist:
        from django.http import Http404
        raise Http404("Produktgruppe nicht gefunden")

    # Alle Produkte dieser Gruppe
    produkte = BillaProdukt.objects.filter(
        produktgruppe=produktgruppe_obj  # ✅ GEÄNDERT
    ).annotate(
        gesamtausgaben=Sum('artikel__gesamtpreis')
    ).prefetch_related('preishistorie').order_by('-anzahl_kaeufe')

    if not produkte.exists():
        from django.http import Http404
        raise Http404("Produktgruppe nicht gefunden")

    # Überkategorie und Icon
    ueberkategorie = produktgruppe_obj.ueberkategorie
    KATEGORIE_ICONS = {
        'Gemüse': 'bi-basket',
        # ... restliche Icons
    }
    icon = KATEGORIE_ICONS.get(ueberkategorie.name, 'bi-box-seam')

    # Statistiken
    stats = produkte.aggregate(
        gesamt_produkte=Count('id'),
        gesamt_kaeufe=Sum('anzahl_kaeufe'),
        durchschnittspreis=Avg('durchschnittspreis'),
        min_preis=Min('letzter_preis'),
        max_preis=Max('letzter_preis'),
        gesamt_ausgaben=Sum('gesamtausgaben')
    )

    # Letzte Käufe
    letzte_kaeufe = BillaArtikel.objects.filter(
        produkt__produktgruppe=produktgruppe_obj  # ✅ GEÄNDERT
    ).select_related(
        'einkauf', 'produkt'
    ).order_by('-einkauf__datum')[:30]

    # Preisentwicklung
    produkte_mit_preisen = []
    for produkt in produkte:
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
                produkte_mit_preisen.append({
                    'produkt': produkt,
                    'min_preis': min_preis,
                    'max_preis': max_preis,
                    'diff': diff,
                    'diff_pct': diff_pct
                })

    produkte_mit_preisen.sort(key=lambda x: x['diff_pct'], reverse=True)

    # Preisentwicklung Gruppe
    preis_historie_raw = BillaPreisHistorie.objects.filter(
        produkt__produktgruppe=produktgruppe_obj  # ✅ GEÄNDERT
    ).values('datum').annotate(
        durchschnitt=Avg('preis')
    ).order_by('datum')

    preis_historie_simple = []
    for entry in preis_historie_raw:
        preis_historie_simple.append({
            'datum': entry['datum'].strftime('%Y-%m-%d'),
            'durchschnitt': float(entry['durchschnitt']) if entry['durchschnitt'] else 0
        })

    # Detail-Historie mit min/max
    preis_historie_detail_raw = BillaPreisHistorie.objects.filter(
        produkt__produktgruppe=produktgruppe_obj  # ✅ GEÄNDERT
    ).values('datum').annotate(
        durchschnitt=Avg('preis'),
        min_preis=Min('preis'),
        max_preis=Max('preis')
    ).order_by('datum')

    preis_historie_detail = []
    for entry in preis_historie_detail_raw:
        preis_historie_detail.append({
            'datum': entry['datum'].strftime('%Y-%m-%d'),
            'durchschnitt': float(entry['durchschnitt']) if entry['durchschnitt'] else 0,
            'min_preis': float(entry['min_preis']) if entry['min_preis'] else 0,
            'max_preis': float(entry['max_preis']) if entry['max_preis'] else 0
        })

    context = {
        'produktgruppe': produktgruppe_obj.name,  # ✅ GEÄNDERT
        'produktgruppe_obj': produktgruppe_obj,  # ✅ NEU für Template
        'ueberkategorie': ueberkategorie.name,  # ✅ GEÄNDERT
        'icon': icon,
        'produkte': produkte,
        'stats': stats,
        'letzte_kaeufe': letzte_kaeufe,
        'produkte_mit_preisen': produkte_mit_preisen,
        'preis_historie_json': json.dumps(preis_historie_simple),
        'preis_historie_detail_json': json.dumps(preis_historie_detail)
    }

    return render(request, 'billa/billa_produktgruppe_detail.html', context)


# ============================================================================
# PREISENTWICKLUNG - ÜBERKATEGORIEN
# ============================================================================

@login_required
def billa_ueberkategorien_liste(request):
    """Zeigt alle Überkategorien mit aggregierter Preisentwicklung"""

    # ✅ GEÄNDERT: Aggregiere über Überkategorien-Tabelle
    ueberkategorien_base = BillaUeberkategorie.objects.annotate(
        anzahl_produkte=Count('produkte', distinct=True),
        anzahl_kaeufe=Sum('produkte__anzahl_kaeufe')
    ).order_by('name')

    ueberkategorien = []

    for kat_obj in ueberkategorien_base:
        # Preisentwicklung über Zeit
        preis_stats = BillaPreisHistorie.objects.filter(
            produkt__ueberkategorie=kat_obj  # ✅ GEÄNDERT: Objekt statt String
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
                produkt__ueberkategorie=kat_obj  # ✅ GEÄNDERT
            ).values('datum').annotate(
                durchschnitt=Avg('preis')
            ).order_by('datum')[:60]

            preis_historie_converted = [
                {
                    'datum': h['datum'],
                    'durchschnitt': float(h['durchschnitt']) if h['durchschnitt'] else 0.0
                }
                for h in preis_historie_raw
            ]

            ueberkategorien.append({
                'id': kat_obj.id,  # ✅ NEU
                'name': kat_obj.name,
                'anzahl_produkte': kat_obj.anzahl_produkte or 0,
                'anzahl_kaeufe': kat_obj.anzahl_kaeufe or 0,
                'min_preis': float(min_preis),
                'max_preis': float(max_preis),
                'avg_preis': float(preis_stats['avg_preis']) if preis_stats['avg_preis'] else 0.0,
                'diff': float(diff),
                'diff_pct': float(diff_pct),
                'preis_historie': preis_historie_converted
            })

    # Sortiere nach Preisänderung
    ueberkategorien.sort(key=lambda x: x['diff_pct'], reverse=True)

    context = {
        'ueberkategorien': ueberkategorien
    }

    return render(request, 'billa/billa_ueberkategorien_liste.html', context)


@login_required
def billa_ueberkategorie_detail(request, ueberkategorie):
    """Detailansicht einer Überkategorie"""

    # Hole Überkategorie-Objekt per ID
    try:
        ueberkategorie_obj = BillaUeberkategorie.objects.get(id=ueberkategorie_id)
    except BillaUeberkategorie.DoesNotExist:
        from django.http import Http404
        raise Http404("Überkategorie nicht gefunden")

    # Produktgruppen dieser Überkategorie
    produktgruppen_base = BillaProduktgruppe.objects.filter(
        ueberkategorie=ueberkategorie_obj  # ✅ GEÄNDERT
    ).annotate(
        anzahl_produkte=Count('produkte', distinct=True),
        anzahl_kaeufe=Sum('produkte__anzahl_kaeufe'),
        durchschnittspreis=Avg('produkte__durchschnittspreis')
    ).order_by('-anzahl_kaeufe')

    KATEGORIE_ICONS = {
        'Gemüse': 'bi-basket',
        'Obst': 'bi-apple',
        'Milchprodukte': 'bi-cup-straw',
        'Fleisch & Wurst': 'bi-shop',
        'Getränke': 'bi-cup',
        'Brot & Backwaren': 'bi-bread-slice',
        'Tiefkühl': 'bi-snow',
        'Süßigkeiten': 'bi-candy',
        'Haushalt & Reinigung': 'bi-house',
        'Hygiene & Kosmetik': 'bi-droplet',
        'Sonstiges': 'bi-three-dots'
    }
    icon = KATEGORIE_ICONS.get(ueberkategorie_obj.name, 'bi-box-seam')

    produktgruppen_list = []
    for gruppe in produktgruppen_base:
        produktgruppen_list.append({
            'id': gruppe.id,
            'name': gruppe.name,
            'anzahl_produkte': gruppe.anzahl_produkte,
            'anzahl_kaeufe': gruppe.anzahl_kaeufe or 0,
            'durchschnittspreis': gruppe.durchschnittspreis,
            'icon': icon
        })

    # Statistiken
    stats = BillaProdukt.objects.filter(
        ueberkategorie=ueberkategorie_obj  # ✅ GEÄNDERT
    ).aggregate(
        gesamt_produkte=Count('id', distinct=True),
        gesamt_kaeufe=Sum('anzahl_kaeufe'),
        durchschnittspreis=Avg('durchschnittspreis'),
        min_preis=Min('letzter_preis'),
        max_preis=Max('letzter_preis'),
        gesamt_ausgaben=Sum('artikel__gesamtpreis')
    )

    # Produktgruppen mit Preisänderungen
    produktgruppen_mit_preisen = []

    for gruppe in produktgruppen_base:
        preis_stats = BillaPreisHistorie.objects.filter(
            produkt__produktgruppe=gruppe  # ✅ GEÄNDERT
        ).aggregate(
            min_preis=Min('preis'),
            max_preis=Max('preis'),
            avg_preis=Avg('preis'),
            count=Count('id')
        )

        if preis_stats['count'] >= 2 and preis_stats['min_preis']:
            min_preis = preis_stats['min_preis']
            max_preis = preis_stats['max_preis']
            diff = max_preis - min_preis
            diff_pct = (diff / min_preis * 100) if min_preis > 0 else 0

            preis_historie_raw = BillaPreisHistorie.objects.filter(
                produkt__produktgruppe=gruppe  # ✅ GEÄNDERT
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
                'id': gruppe.id,
                'name': gruppe.name,
                'anzahl_produkte': gruppe.anzahl_produkte,
                'anzahl_kaeufe': gruppe.anzahl_kaeufe,
                'min_preis': float(min_preis),
                'max_preis': float(max_preis),
                'avg_preis': float(preis_stats['avg_preis']) if preis_stats['avg_preis'] else 0,
                'diff': float(diff),
                'diff_pct': float(diff_pct),
                'preis_historie': preis_historie
            })

    produktgruppen_mit_preisen.sort(key=lambda x: x['diff_pct'], reverse=True)

    # Preisentwicklung der gesamten Überkategorie
    preis_historie_simple = []
    for entry in BillaPreisHistorie.objects.filter(
            produkt__ueberkategorie=ueberkategorie_obj  # ✅ GEÄNDERT
    ).values('datum').annotate(
        durchschnitt=Avg('preis')
    ).order_by('datum'):
        preis_historie_simple.append({
            'datum': entry['datum'].strftime('%Y-%m-%d'),
            'durchschnitt': float(entry['durchschnitt']) if entry['durchschnitt'] else 0
        })

    preis_historie_detail = []
    for entry in BillaPreisHistorie.objects.filter(
            produkt__ueberkategorie=ueberkategorie_obj  # ✅ GEÄNDERT
    ).values('datum').annotate(
        durchschnitt=Avg('preis'),
        min_preis=Min('preis'),
        max_preis=Max('preis')
    ).order_by('datum'):
        preis_historie_detail.append({
            'datum': entry['datum'].strftime('%Y-%m-%d'),
            'durchschnitt': float(entry['durchschnitt']) if entry['durchschnitt'] else 0,
            'min_preis': float(entry['min_preis']) if entry['min_preis'] else 0,
            'max_preis': float(entry['max_preis']) if entry['max_preis'] else 0
        })

    # Top Produkte
    top_produkte = BillaProdukt.objects.filter(
        ueberkategorie=ueberkategorie_obj  # ✅ GEÄNDERT
    ).order_by('-anzahl_kaeufe')[:10]

    stats['anzahl_produktgruppen'] = len(produktgruppen_list)

    context = {
        'ueberkategorie': ueberkategorie_obj.name,
        'ueberkategorie_obj': ueberkategorie_obj,  # ✅ NEU
        'icon': icon,
        'stats': stats,
        'produktgruppen': produktgruppen_list,
        'produktgruppen_mit_preisen': json.dumps(produktgruppen_mit_preisen),
        'top_produkte': top_produkte,
        'preis_historie_json': json.dumps(preis_historie_simple),
        'preis_historie_detail_json': json.dumps(preis_historie_detail)
    }

    return render(request, 'billa/billa_ueberkategorie_detail.html', context)



# ============================================================================
# MARKEN - ÜBERSICHT
# ============================================================================

@login_required
def billa_marken_liste(request):
    """Zeigt alle Marken mit Statistiken"""
    ueberkategorie_filter = request.GET.get('ueberkategorie', 'alle')
    produktgruppe_filter = request.GET.get('produktgruppe', 'alle')
    suche = request.GET.get('suche', '')
    sortierung = request.GET.get('sort', '-anzahl_kaeufe')

    # Basis-Queryset für Marken
    marken = BillaProdukt.objects.exclude(
        Q(marke__isnull=True) | Q(marke='')
    )

    # ✅ Filter nach Überkategorie (mit ID!)
    if ueberkategorie_filter and ueberkategorie_filter != 'alle':
        marken = marken.filter(ueberkategorie__id=ueberkategorie_filter)

    # ✅ Filter nach Produktgruppe (mit ID!)
    if produktgruppe_filter and produktgruppe_filter != 'alle':
        marken = marken.filter(produktgruppe__id=produktgruppe_filter)

    # Aggregiere nach Marke
    marken = marken.values('marke').annotate(
        anzahl_produkte=Count('id'),
        anzahl_kaeufe=Sum('anzahl_kaeufe'),
        durchschnittspreis=Avg('durchschnittspreis'),
        aktueller_preis=Avg('letzter_preis')
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

    # ✅ GEÄNDERT: Filter-Optionen aus den neuen Tabellen
    alle_ueberkategorien = BillaUeberkategorie.objects.filter(
        produkte__marke__isnull=False
    ).distinct().order_by('name')

    alle_produktgruppen = BillaProduktgruppe.objects.filter(
        produkte__marke__isnull=False
    ).distinct().order_by('name')

    context = {
        'marken': list(marken),
        'ueberkategorien': alle_ueberkategorien,  # ✅ Jetzt Objekte statt Strings
        'produktgruppen': alle_produktgruppen,    # ✅ Jetzt Objekte statt Strings
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
    """Detailansicht einer spezifischen Marke mit integrierter Preisentwicklung"""
    import json

    # Prüfe ob Marke existiert
    if not BillaProdukt.objects.filter(marke=marke).exists():
        from django.http import Http404
        raise Http404("Marke nicht gefunden")

    # Filter aus Query-Parametern
    ueberkategorie_filter = request.GET.get('ueberkategorie', 'alle')
    produktgruppe_filter = request.GET.get('produktgruppe', 'alle')
    sortierung = request.GET.get('sort', '-anzahl_kaeufe')

    # Basis-Queryset mit select_related für Performance
    produkte_base = BillaProdukt.objects.filter(marke=marke).select_related(
        'ueberkategorie', 'produktgruppe'
    )

    # Filter anwenden - ✅ GEÄNDERT: Jetzt mit IDs!
    produkte = produkte_base
    if ueberkategorie_filter and ueberkategorie_filter != 'alle':
        produkte = produkte.filter(ueberkategorie__id=ueberkategorie_filter)
    if produktgruppe_filter and produktgruppe_filter != 'alle':
        produkte = produkte.filter(produktgruppe__id=produktgruppe_filter)

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
        gesamt_ausgaben=Sum('artikel__gesamtpreis')
    )

    # ✅ GEÄNDERT: Produktgruppen mit Foreign Key Relation
    produktgruppen = BillaProduktgruppe.objects.filter(
        produkte__marke=marke
    ).select_related('ueberkategorie').annotate(
        anzahl_produkte=Count('produkte', distinct=True),
        anzahl_kaeufe=Sum('produkte__anzahl_kaeufe')
    ).order_by('-anzahl_kaeufe')

    # Icons
    KATEGORIE_ICONS = {
        'Gemüse': 'bi-basket',
        'Obst': 'bi-apple',
        'Milchprodukte': 'bi-cup-straw',
        'Fleisch & Wurst': 'bi-shop',
        'Getränke': 'bi-cup',
        'Brot & Backwaren': 'bi-bread-slice',
        'Tiefkühl': 'bi-snow',
        'Süßigkeiten': 'bi-candy',
        'Haushalt & Reinigung': 'bi-house',
        'Hygiene & Kosmetik': 'bi-droplet',
        'Sonstiges': 'bi-three-dots'
    }

    produktgruppen_list = []
    for gruppe in produktgruppen:
        produktgruppen_list.append({
            'id': gruppe.id,  # ✅ NEU
            'name': gruppe.name,
            'ueberkategorie': gruppe.ueberkategorie.name,
            'ueberkategorie_id': gruppe.ueberkategorie.id,  # ✅ NEU
            'anzahl_produkte': gruppe.anzahl_produkte,
            'anzahl_kaeufe': gruppe.anzahl_kaeufe or 0,
            'icon': KATEGORIE_ICONS.get(gruppe.ueberkategorie.name, 'bi-tag')
        })

    # ✅ GEÄNDERT: Filter-Optionen aus den neuen Tabellen
    alle_ueberkategorien = BillaUeberkategorie.objects.filter(
        produkte__marke=marke
    ).distinct().order_by('name')

    alle_produktgruppen = BillaProduktgruppe.objects.filter(
        produkte__marke=marke
    ).distinct().order_by('name')

    # Preisentwicklung
    produkte_mit_preisen = []
    for produkt in produkte:
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
                produkte_mit_preisen.append({
                    'produkt': produkt,
                    'min_preis': min_preis,
                    'max_preis': max_preis,
                    'diff': diff,
                    'diff_pct': diff_pct
                })

    produkte_mit_preisen.sort(key=lambda x: x['diff_pct'], reverse=True)

    # Preisentwicklung der gesamten Marke
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

    preis_historie_detail = []
    for entry in BillaPreisHistorie.objects.filter(
        produkt__marke=marke
    ).values('datum').annotate(
        durchschnitt=Avg('preis'),
        min_preis=Min('preis'),
        max_preis=Max('preis')
    ).order_by('datum'):
        preis_historie_detail.append({
            'datum': entry['datum'].strftime('%Y-%m-%d'),
            'durchschnitt': float(entry['durchschnitt']) if entry['durchschnitt'] else 0,
            'min_preis': float(entry['min_preis']) if entry['min_preis'] else 0,
            'max_preis': float(entry['max_preis']) if entry['max_preis'] else 0
        })

    context = {
        'marke': marke,
        'produkte': produkte,
        'stats': stats,
        'produktgruppen': produktgruppen_list,
        'ueberkategorien': alle_ueberkategorien,  # ✅ Jetzt Objekte
        'alle_produktgruppen': alle_produktgruppen,  # ✅ Jetzt Objekte
        'selected_ueberkategorie': ueberkategorie_filter or 'alle',
        'selected_produktgruppe': produktgruppe_filter or 'alle',
        'sortierung': sortierung,
        'produkte_mit_preisen': produkte_mit_preisen,
        'preis_historie_json': json.dumps(preis_historie_simple),
        'preis_historie_detail_json': json.dumps(preis_historie_detail)
    }

    return render(request, 'billa/billa_marke_detail.html', context)


@login_required
@require_POST
def ajax_create_kategorie(request):
    """AJAX-Endpoint zum Erstellen neuer Überkategorien oder Produktgruppen"""
    try:
        data = json.loads(request.body)
        typ = data.get('typ')
        name = data.get('name', '').strip()
        ueberkategorie_id = data.get('ueberkategorie_id')  # ✅ GEÄNDERT: ID statt Name

        if not name:
            return JsonResponse({
                'status': 'error',
                'message': 'Name darf nicht leer sein'
            }, status=400)

        if typ == 'ueberkategorie':
            # Prüfe ob bereits existiert
            if BillaUeberkategorie.objects.filter(name=name).exists():
                return JsonResponse({
                    'status': 'error',
                    'message': f'Überkategorie "{name}" existiert bereits'
                }, status=400)

            # Erstelle neue Überkategorie
            obj = BillaUeberkategorie.objects.create(name=name)

            logger.info(f"Neue Überkategorie erstellt: {name} (ID: {obj.id})")

            return JsonResponse({
                'status': 'success',
                'id': obj.id,
                'name': obj.name,
                'message': f'Überkategorie "{name}" erfolgreich erstellt'
            })

        elif typ == 'produktgruppe':
            if not ueberkategorie_id:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Überkategorie muss angegeben werden'
                }, status=400)

            try:
                ueberkategorie = BillaUeberkategorie.objects.get(id=ueberkategorie_id)
            except BillaUeberkategorie.DoesNotExist:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Überkategorie nicht gefunden'
                }, status=400)

            # Prüfe ob bereits existiert
            if BillaProduktgruppe.objects.filter(
                    name=name,
                    ueberkategorie=ueberkategorie
            ).exists():
                return JsonResponse({
                    'status': 'error',
                    'message': f'Produktgruppe "{name}" existiert bereits'
                }, status=400)

            # Erstelle neue Produktgruppe
            obj = BillaProduktgruppe.objects.create(
                name=name,
                ueberkategorie=ueberkategorie
            )

            logger.info(f"Neue Produktgruppe erstellt: {name} in {ueberkategorie.name} (ID: {obj.id})")

            return JsonResponse({
                'status': 'success',
                'id': obj.id,
                'name': obj.name,
                'ueberkategorie_id': ueberkategorie.id,
                'message': f'Produktgruppe "{name}" erfolgreich erstellt'
            })

        else:
            return JsonResponse({
                'status': 'error',
                'message': 'Ungültiger Typ'
            }, status=400)

    except Exception as e:
        logger.error(f"Fehler beim Erstellen der Kategorie: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)