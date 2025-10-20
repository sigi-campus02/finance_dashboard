from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from decimal import Decimal
import logging
import os

from .models import BitpandaSnapshot
from .bitpanda_service import BitpandaService

logger = logging.getLogger(__name__)


@login_required
def bitpanda_dashboard(request):
    """
    Hauptseite des Bitpanda Dashboards
    """
    # Prüfe ob API Key in Environment gesetzt ist
    has_api_key = bool(os.environ.get('BITPANDA_API_KEY'))

    if not has_api_key:
        context = {
            'has_api_key': False,
            'portfolio': None,
        }
        return render(request, 'bitpanda/bitpanda_dashboard.html', context)

    try:
        # Hole aktuelles Portfolio
        service = BitpandaService()
        portfolio = service.get_portfolio_summary()

        # Hole letzte Snapshots für Chart
        recent_snapshots = BitpandaSnapshot.objects.filter(
            user=request.user
        ).order_by('-snapshot_date')[:30]

        # Letzter Snapshot für "last_sync" Info
        last_snapshot = recent_snapshots.first() if recent_snapshots else None

        context = {
            'has_api_key': True,
            'portfolio': portfolio,
            'last_sync': last_snapshot.snapshot_date if last_snapshot else None,
            'recent_snapshots': recent_snapshots,
        }

    except ValueError as e:
        # API Key ungültig
        logger.error(f"Bitpanda API Key Fehler: {e}")
        messages.error(request, f"API Key Problem: {str(e)}")
        context = {
            'has_api_key': False,
            'portfolio': None,
        }
    except Exception as e:
        logger.error(f"Fehler beim Laden des Bitpanda Dashboards: {e}")
        messages.error(request, f"Fehler beim Laden der Bitpanda Daten: {str(e)}")
        context = {
            'has_api_key': True,
            'portfolio': None,
        }

    return render(request, 'bitpanda/bitpanda_dashboard.html', context)


@login_required
@require_http_methods(["POST"])
def bitpanda_sync(request):
    """
    Synchronisiert Bitpanda Daten und erstellt Snapshot
    """
    try:
        service = BitpandaService()

        # Hole Portfolio-Daten
        portfolio = service.get_portfolio_summary()

        # Berechne Werte
        total_fiat_eur = Decimal(str(portfolio.get('total_fiat_eur', 0)))

        # Erstelle Snapshot
        snapshot = BitpandaSnapshot.objects.create(
            user=request.user,
            total_crypto_value_eur=Decimal('0'),
            total_fiat_value_eur=total_fiat_eur,
            total_commodities_value_eur=Decimal('0'),
            total_value_eur=total_fiat_eur,
            raw_data=portfolio
        )

        messages.success(request, f"Synchronisation erfolgreich! Portfolio-Wert: €{snapshot.total_value_eur}")

    except ValueError as e:
        messages.error(request, f"API Key Problem: {str(e)}")
    except Exception as e:
        logger.error(f"Fehler bei Bitpanda Sync: {e}")
        messages.error(request, f"Fehler bei der Synchronisation: {str(e)}")

    return redirect('bitpanda:bitpanda_dashboard')


@login_required
def api_bitpanda_portfolio_chart(request):
    """
    API Endpoint für Portfolio Chart Daten
    """
    try:
        snapshots = BitpandaSnapshot.objects.filter(
            user=request.user
        ).order_by('snapshot_date')[:90]  # Letzte 90 Snapshots

        data = {
            'labels': [s.snapshot_date.strftime('%Y-%m-%d %H:%M') for s in snapshots],
            'datasets': [
                {
                    'label': 'Gesamtwert',
                    'data': [float(s.total_value_eur) for s in snapshots],
                    'borderColor': 'rgb(75, 192, 192)',
                    'tension': 0.1
                },
                {
                    'label': 'Crypto',
                    'data': [float(s.total_crypto_value_eur) for s in snapshots],
                    'borderColor': 'rgb(255, 159, 64)',
                    'tension': 0.1
                },
                {
                    'label': 'Fiat',
                    'data': [float(s.total_fiat_value_eur) for s in snapshots],
                    'borderColor': 'rgb(54, 162, 235)',
                    'tension': 0.1
                }
            ]
        }

        return JsonResponse(data)

    except Exception as e:
        logger.error(f"Fehler beim Laden der Chart-Daten: {e}")
        return JsonResponse({'error': str(e)}, status=500)