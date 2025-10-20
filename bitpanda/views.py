# bitpanda/views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from decimal import Decimal
from collections import defaultdict
from datetime import date
import logging
from django.shortcuts import redirect
from .models import BitpandaHolding, BitpandaAssetValue

logger = logging.getLogger(__name__)


@login_required
def bitpanda_dashboard(request):
    """
    Hauptseite des Bitpanda Dashboards - nur mit historischen Daten aus BitpandaAssetValue
    """
    try:
        # Hole alle Holdings
        holdings = BitpandaHolding.objects.filter(user=request.user)

        if not holdings.exists():
            context = {'has_data': False}
            return render(request, 'bitpanda/bitpanda_dashboard.html', context)

        # Berechne Portfolio aus historischen Transaktionen
        today = date.today()

        portfolio = {
            'crypto': [],
            'stocks': [],
            'etfs': [],
            'commodities': [],
            'total_value': Decimal('0'),
            'total_invested': Decimal('0'),
            'crypto_value': Decimal('0'),
            'stock_value': Decimal('0'),
            'etf_value': Decimal('0'),
            'commodity_value': Decimal('0'),
            'crypto_invested': Decimal('0'),
            'stock_invested': Decimal('0'),
            'etf_invested': Decimal('0'),
            'commodity_invested': Decimal('0'),
            'crypto_profit_loss': Decimal('0'),
            'stock_profit_loss': Decimal('0'),
            'etf_profit_loss': Decimal('0'),
            'commodity_profit_loss': Decimal('0'),
        }

        for holding in holdings:
            # Hole alle Transaktionen für dieses Asset
            transactions = BitpandaAssetValue.objects.filter(
                holding=holding,
                date__lte=today
            ).order_by('date')

            if not transactions.exists():
                continue

            # Berechne aktuellen Bestand (Summe aller units)
            total_units = Decimal('0')
            for tx in transactions:
                if tx.units:
                    total_units += tx.units

            # Überspringe wenn kein Bestand mehr
            if total_units <= 0:
                continue

            # Hole letzten bekannten Preis
            last_transaction = transactions.last()
            current_price = last_transaction.price_per_unit

            # Berechne investierten Betrag (nur Käufe = positive units)
            total_invested = Decimal('0')
            for tx in transactions:
                if tx.payed and tx.units and tx.units > 0:
                    total_invested += tx.payed

            # Berechne aktuellen Wert
            current_value = total_units * current_price

            # Gewinn/Verlust
            profit_loss = current_value - total_invested
            profit_loss_pct = (profit_loss / total_invested * 100) if total_invested > 0 else Decimal('0')

            asset_data = {
                'asset': holding.asset,
                'balance': total_units,
                'current_price': current_price,
                'current_value': current_value,
                'invested': total_invested,
                'profit_loss': profit_loss,
                'profit_loss_pct': profit_loss_pct,
            }

            # Sortiere nach Asset Class
            if holding.asset_class == 'Cryptocurrency':
                portfolio['crypto'].append(asset_data)
                portfolio['crypto_value'] += current_value
                portfolio['crypto_invested'] += total_invested
                portfolio['crypto_profit_loss'] += profit_loss

            elif holding.asset_class == 'Stock (derivative)':
                portfolio['stocks'].append(asset_data)
                portfolio['stock_value'] += current_value
                portfolio['stock_invested'] += total_invested
                portfolio['stock_profit_loss'] += profit_loss

            elif holding.asset_class in ['ETF (derivative)', 'ETF']:
                portfolio['etfs'].append(asset_data)
                portfolio['etf_value'] += current_value
                portfolio['etf_invested'] += total_invested
                portfolio['etf_profit_loss'] += profit_loss

            elif holding.asset_class == 'Commodity':
                portfolio['commodities'].append(asset_data)
                portfolio['commodity_value'] += current_value
                portfolio['commodity_invested'] += total_invested
                portfolio['commodity_profit_loss'] += profit_loss

            # Addiere zu Total
            portfolio['total_invested'] += total_invested

        # Berechne Gesamtwerte
        portfolio['total_value'] = (
                portfolio['crypto_value'] +
                portfolio['stock_value'] +
                portfolio['etf_value'] +
                portfolio['commodity_value']
        )
        portfolio['total_profit_loss'] = portfolio['total_value'] - portfolio['total_invested']
        portfolio['total_profit_loss_pct'] = (
            (portfolio['total_profit_loss'] / portfolio['total_invested'] * 100)
            if portfolio['total_invested'] > 0 else Decimal('0')
        )

        # Performance Daten
        performance = calculate_performance(request.user, portfolio)

        context = {
            'has_data': True,
            'portfolio': portfolio,
            'performance': performance,
        }

    except Exception as e:
        logger.error(f"Fehler beim Laden des Bitpanda Dashboards: {e}")
        messages.error(request, f"Fehler beim Laden: {str(e)}")
        context = {
            'has_data': False,
            'error': str(e),
        }

    return render(request, 'bitpanda/bitpanda_dashboard.html', context)


def calculate_performance(user, portfolio):
    """Berechnet Portfolio-Performance über Zeit aus historischen Daten"""
    # Hole alle Transaktionen des Users
    all_holdings = BitpandaHolding.objects.filter(user=user)

    # Sammle alle Transaktionen
    all_transactions = []
    for holding in all_holdings:
        transactions = BitpandaAssetValue.objects.filter(holding=holding)
        for tx in transactions:
            all_transactions.append({
                'date': tx.date,
                'asset': holding.asset,
                'payed': tx.payed if tx.payed else Decimal('0'),
                'units': tx.units if tx.units else Decimal('0'),
                'price': tx.price_per_unit,
            })

    # Sortiere nach Datum
    all_transactions.sort(key=lambda x: x['date'])

    if not all_transactions:
        return {
            'data': [],
            'total_invested': 0,
            'current_value': float(portfolio['total_value']),
        }

    # Gruppiere nach Monat
    monthly_data = defaultdict(lambda: {'invested': Decimal('0')})

    for tx in all_transactions:
        if tx['units'] > 0:  # Nur Käufe
            month_key = tx['date'].strftime('%Y-%m')
            monthly_data[month_key]['invested'] += abs(tx['payed'])

    # Erstelle kumulative Daten
    cumulative = Decimal('0')
    performance_data = []
    current_value = portfolio['total_value']

    for month_key in sorted(monthly_data.keys()):
        cumulative += monthly_data[month_key]['invested']
        performance_data.append({
            'date': month_key,
            'invested': float(cumulative),
            'current_value': float(current_value),
        })

    return {
        'data': performance_data,
        'total_invested': float(cumulative),
        'current_value': float(current_value),
    }


@login_required
def api_bitpanda_portfolio_chart(request):
    """API Endpoint für Portfolio Performance Chart - Entwicklung über Zeit"""
    try:
        holdings = BitpandaHolding.objects.filter(user=request.user)

        if not holdings.exists():
            return JsonResponse({'labels': [], 'datasets': []})

        # Sammle alle Transaktionen
        all_data = defaultdict(lambda: defaultdict(lambda: {
            'value': Decimal('0'),
            'units': Decimal('0'),
            'price': Decimal('0')
        }))

        all_months = set()

        for holding in holdings:
            transactions = BitpandaAssetValue.objects.filter(holding=holding).order_by('date')

            for tx in transactions:
                month_key = tx.date.strftime('%Y-%m')
                all_months.add(month_key)

                # Summiere units für aktuellen Bestand
                if tx.units:
                    all_data[holding.asset][month_key]['units'] += tx.units

                # Letzter bekannter Preis
                all_data[holding.asset][month_key]['price'] = tx.price_per_unit

        sorted_months = sorted(all_months)

        # Erstelle Datasets pro Asset
        datasets = []
        colors = [
            'rgb(255, 99, 132)', 'rgb(54, 162, 235)', 'rgb(255, 206, 86)',
            'rgb(75, 192, 192)', 'rgb(153, 102, 255)', 'rgb(255, 159, 64)',
            'rgb(199, 199, 199)', 'rgb(83, 102, 255)', 'rgb(255, 99, 255)',
            'rgb(99, 255, 132)', 'rgb(132, 99, 255)', 'rgb(255, 206, 132)',
        ]

        color_index = 0

        for asset in sorted(all_data.keys()):
            cumulative_units = Decimal('0')
            data_points = []
            last_price = Decimal('0')

            for month in sorted_months:
                if month in all_data[asset]:
                    cumulative_units += all_data[asset][month]['units']
                    if all_data[asset][month]['price'] > 0:
                        last_price = all_data[asset][month]['price']

                # Aktueller Wert = Bestand × letzter Preis
                current_value = cumulative_units * last_price if last_price > 0 else Decimal('0')
                data_points.append(float(current_value))

            # Nur Assets mit positivem Bestand anzeigen
            if cumulative_units > 0:
                datasets.append({
                    'label': asset,
                    'data': data_points,
                    'borderColor': colors[color_index % len(colors)],
                    'backgroundColor': colors[color_index % len(colors)].replace('rgb', 'rgba').replace(')', ', 0.1)'),
                    'tension': 0.4,
                    'fill': False,
                })
                color_index += 1

        data = {
            'labels': sorted_months,
            'datasets': datasets
        }

        return JsonResponse(data)

    except Exception as e:
        logger.error(f"Chart API Error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def api_bitpanda_asset_allocation(request):
    """API Endpoint für Asset Allocation Pie Chart"""
    try:
        holdings = BitpandaHolding.objects.filter(user=request.user)

        if not holdings.exists():
            return JsonResponse({'labels': [], 'datasets': [{'data': []}]})

        today = date.today()

        crypto_value = Decimal('0')
        stock_value = Decimal('0')
        etf_value = Decimal('0')
        commodity_value = Decimal('0')

        for holding in holdings:
            transactions = BitpandaAssetValue.objects.filter(
                holding=holding,
                date__lte=today
            ).order_by('date')

            if not transactions.exists():
                continue

            # Berechne aktuellen Bestand
            total_units = sum(tx.units for tx in transactions if tx.units) or Decimal('0')

            if total_units <= 0:
                continue

            # Letzter Preis
            last_price = transactions.last().price_per_unit
            current_value = total_units * last_price

            # Addiere zu entsprechender Kategorie
            if holding.asset_class == 'Cryptocurrency':
                crypto_value += current_value
            elif holding.asset_class == 'Stock (derivative)':
                stock_value += current_value
            elif holding.asset_class in ['ETF (derivative)', 'ETF']:
                etf_value += current_value
            elif holding.asset_class == 'Commodity':
                commodity_value += current_value

        data = {
            'labels': [],
            'datasets': [{
                'data': [],
                'backgroundColor': [
                    'rgb(255, 159, 64)',  # Crypto
                    'rgb(54, 162, 235)',  # Stocks
                    'rgb(67, 233, 123)',  # ETFs
                    'rgb(240, 147, 251)',  # Commodities
                ],
            }]
        }

        if crypto_value > 0:
            data['labels'].append('Krypto')
            data['datasets'][0]['data'].append(float(crypto_value))

        if stock_value > 0:
            data['labels'].append('Aktien')
            data['datasets'][0]['data'].append(float(stock_value))

        if etf_value > 0:
            data['labels'].append('ETFs')
            data['datasets'][0]['data'].append(float(etf_value))

        if commodity_value > 0:
            data['labels'].append('Rohstoffe')
            data['datasets'][0]['data'].append(float(commodity_value))

        return JsonResponse(data)

    except Exception as e:
        logger.error(f"Allocation API Error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# bitpanda/views.py

@login_required
def update_prices(request):
    """Manuelle Preisaktualisierung - erstellt neue Einträge in BitpandaAssetValue"""
    from datetime import date

    holdings = BitpandaHolding.objects.filter(user=request.user).order_by('asset')
    today = date.today()

    if request.method == 'POST':
        updated_count = 0
        errors = []

        for holding in holdings:
            price_key = f'price_{holding.id}'
            price_value = request.POST.get(price_key, '').strip()

            if price_value:
                try:
                    new_price = Decimal(price_value)

                    if new_price > 0:
                        # Prüfe ob heute schon ein Eintrag existiert
                        existing = BitpandaAssetValue.objects.filter(
                            holding=holding,
                            date=today
                        ).first()

                        if existing:
                            # Update existierenden Eintrag
                            existing.price_per_unit = new_price
                            existing.save()
                            updated_count += 1
                        else:
                            # Erstelle neuen Eintrag (nur Preis, keine Transaktion)
                            BitpandaAssetValue.objects.create(
                                holding=holding,
                                date=today,
                                price_per_unit=new_price,
                                payed=None,
                                units=None
                            )
                            updated_count += 1
                    else:
                        errors.append(f'{holding.asset}: Preis muss größer als 0 sein')

                except (ValueError, Decimal.InvalidOperation) as e:
                    errors.append(f'{holding.asset}: Ungültiger Preis')

        if updated_count > 0:
            messages.success(request, f'✓ {updated_count} Preise erfolgreich aktualisiert in BitpandaAssetValue!')

        if errors:
            for error in errors:
                messages.error(request, error)

        if updated_count == 0 and not errors:
            messages.warning(request, '⚠ Keine Preise wurden eingegeben.')

        return redirect('bitpanda:bitpanda_dashboard')

    # GET Request - Zeige Formular
    holdings_with_prices = []
    for holding in holdings:
        # Hole letzten Preis
        last_tx = BitpandaAssetValue.objects.filter(
            holding=holding
        ).order_by('-date').first()

        # Prüfe ob heute schon ein Eintrag existiert
        today_entry = BitpandaAssetValue.objects.filter(
            holding=holding,
            date=today
        ).first()

        holdings_with_prices.append({
            'holding': holding,
            'last_price': last_tx.price_per_unit if last_tx else None,
            'last_date': last_tx.date if last_tx else None,
            'today_price': today_entry.price_per_unit if today_entry else None,
            'has_today_entry': bool(today_entry),
        })

    context = {
        'holdings_with_prices': holdings_with_prices,
        'today': today,
    }

    return render(request, 'bitpanda/update_prices.html', context)