# bitpanda/bitpanda_service.py
import requests
from decimal import Decimal
from typing import Dict, List, Optional
import logging
import os
from datetime import datetime, timedelta
from django.utils import timezone

# Fix für Windows SSL Certificate Problem
try:
    import certifi

    SSL_VERIFY = certifi.where()
except ImportError:
    SSL_VERIFY = True

logger = logging.getLogger(__name__)


class BitpandaService:
    """
    Service-Klasse für Bitpanda API Integration mit Preis-Tracking
    """

    BASE_URL = 'https://api.bitpanda.com/v1'
    COINGECKO_URL = 'https://api.coingecko.com/api/v3'

    # Mapping: Bitpanda Symbol → CoinGecko ID
    CRYPTO_MAPPING = {
        'BTC': 'bitcoin',
        'ETH': 'ethereum',
        'SOL': 'solana',
        'LTC': 'litecoin',
        'ADA': 'cardano',
        'LINK': 'chainlink',
        'SHIB': 'shiba-inu',
        'VET': 'vechain',
        'MANA': 'decentraland',
        'WLD': 'worldcoin-wld',
    }

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get('BITPANDA_API_KEY')

        if not self.api_key:
            raise ValueError(
                "Bitpanda API Key nicht gefunden! "
                "Setze BITPANDA_API_KEY in den Environment Variables."
            )

        self.headers = {
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json'
        }

    def _make_request(self, endpoint: str, method: str = 'GET', params: Optional[Dict] = None) -> Dict:
        """Bitpanda API Request"""
        url = f"{self.BASE_URL}{endpoint}"

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                params=params,
                timeout=30,
                verify=SSL_VERIFY
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error("Bitpanda API: Ungültiger API-Key")
                raise ValueError("Ungültiger Bitpanda API-Key")
            else:
                logger.error(f"Bitpanda API Error: {e}")
                raise
        except Exception as e:
            logger.error(f"Bitpanda API Request fehlgeschlagen: {e}")
            raise

    def get_crypto_prices(self, symbols: List[str]) -> Dict[str, Decimal]:
        """
        Holt aktuelle Crypto-Preise von CoinGecko

        Args:
            symbols: Liste von Crypto-Symbolen (z.B. ['BTC', 'ETH'])

        Returns:
            Dict mit Symbol → EUR Preis
        """
        prices = {}

        # Konvertiere Symbole zu CoinGecko IDs
        coingecko_ids = []
        symbol_to_id = {}

        for symbol in symbols:
            cg_id = self.CRYPTO_MAPPING.get(symbol)
            if cg_id:
                coingecko_ids.append(cg_id)
                symbol_to_id[cg_id] = symbol

        if not coingecko_ids:
            return prices

        try:
            # CoinGecko API Call
            url = f"{self.COINGECKO_URL}/simple/price"
            params = {
                'ids': ','.join(coingecko_ids),
                'vs_currencies': 'eur'
            }

            response = requests.get(url, params=params, timeout=10, verify=SSL_VERIFY)
            response.raise_for_status()
            data = response.json()

            # Konvertiere zurück zu Symbolen
            for cg_id, price_data in data.items():
                symbol = symbol_to_id.get(cg_id)
                if symbol and 'eur' in price_data:
                    prices[symbol] = Decimal(str(price_data['eur']))

        except Exception as e:
            logger.warning(f"Fehler beim Abrufen der Preise von CoinGecko: {e}")

        return prices

    def get_asset_wallets_grouped(self) -> Dict:
        """
        Holt alle Assets gruppiert nach Typ mit aktuellen Werten

        Returns:
            Dict mit Assets nach Kategorien
        """
        try:
            response = self._make_request('/asset-wallets')
            data = response.get('data', {}).get('attributes', {})

            result = {
                'crypto': [],
                'commodities': [],
                'crypto_indices': [],
                'stocks': [],
                'etfs': [],
            }

            # Crypto Assets
            crypto_data = data.get('cryptocoin', {})
            if crypto_data and 'attributes' in crypto_data:
                crypto_wallets = crypto_data['attributes'].get('wallets', [])

                # Sammle alle Symbole für Preis-Abfrage (nur mit Balance > 0)
                symbols = [w['attributes']['cryptocoin_symbol'] for w in crypto_wallets
                           if not w['attributes'].get('deleted', False) and Decimal(w['attributes']['balance']) > 0]

                # Hole Preise
                prices = self.get_crypto_prices(symbols)

                for wallet in crypto_wallets:
                    attrs = wallet['attributes']
                    balance = Decimal(attrs['balance'])

                    # Nur Wallets mit Balance > 0 hinzufügen
                    if not attrs.get('deleted', False) and balance > 0:
                        symbol = attrs['cryptocoin_symbol']
                        price = prices.get(symbol, Decimal('0'))

                        result['crypto'].append({
                            'name': attrs['name'],
                            'symbol': symbol,
                            'balance': balance,
                            'price_eur': price,
                            'value_eur': balance * price,
                        })

            # Commodities (Gold, Silber, etc.)
            commodities = data.get('commodity', {})
            if commodities:
                metal = commodities.get('metal', {})
                if metal and 'attributes' in metal:
                    for wallet in metal['attributes'].get('wallets', []):
                        attrs = wallet['attributes']
                        balance = Decimal(attrs['balance'])

                        # Nur Wallets mit Balance > 0 hinzufügen
                        if not attrs.get('deleted', False) and balance > 0:
                            result['commodities'].append({
                                'name': attrs['name'],
                                'symbol': attrs['cryptocoin_symbol'],
                                'balance': balance,
                                'price_eur': Decimal('0'),  # TODO: Commodity Preise
                                'value_eur': Decimal('0'),
                            })

            # TODO: Weitere Asset-Typen (Stocks, ETFs, Indices)
            # Diese müssen ggf. über andere Bitpanda Endpoints abgerufen werden

            return result

        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Asset-Wallets: {e}")
            return {
                'crypto': [],
                'commodities': [],
                'crypto_indices': [],
                'stocks': [],
                'etfs': [],
            }

    def get_portfolio_summary(self) -> Dict:
        """
        Erstellt Portfolio-Zusammenfassung mit Werten
        """
        assets = self.get_asset_wallets_grouped()

        # Berechne Gesamtwerte pro Kategorie (alles in Decimal)
        crypto_value = sum(Decimal(str(a['value_eur'])) for a in assets['crypto'])
        commodities_value = sum(Decimal(str(a['value_eur'])) for a in assets['commodities'])

        total_value = crypto_value + commodities_value

        return {
            'assets': assets,
            'crypto_value': float(crypto_value),
            'commodities_value': float(commodities_value),
            'stocks_value': 0.0,
            'etfs_value': 0.0,
            'total_value': float(total_value),
        }

    def get_trades_history(self, days: int = 365) -> List[Dict]:
        """
        Holt Trading-Historie für Performance-Berechnung

        Args:
            days: Anzahl Tage zurück

        Returns:
            Liste von Trades sortiert nach Datum
        """
        try:
            response = self._make_request('/trades', params={'page_size': 100})
            trades = response.get('data', [])

            # Filtere nach Zeitraum (timezone-aware)
            cutoff_date = timezone.now() - timedelta(days=days)

            filtered_trades = []
            for trade in trades:
                attrs = trade['attributes']
                # Parse ISO datetime string und mache es timezone-aware
                trade_date_str = attrs['time']['date_iso8601']

                # Versuche datetime zu parsen
                try:
                    # Entferne Zeitzone-String falls vorhanden und parse neu
                    if '+' in trade_date_str:
                        trade_date_str = trade_date_str.split('+')[0]
                    elif 'Z' in trade_date_str:
                        trade_date_str = trade_date_str.replace('Z', '')

                    trade_date = datetime.fromisoformat(trade_date_str)

                    # Mache timezone-aware falls es naive ist
                    if trade_date.tzinfo is None:
                        trade_date = timezone.make_aware(trade_date)

                except (ValueError, AttributeError) as e:
                    logger.warning(f"Konnte Trade-Datum nicht parsen: {trade_date_str}, Error: {e}")
                    continue

                if trade_date >= cutoff_date:
                    filtered_trades.append({
                        'date': trade_date,
                        'type': attrs['type'],  # buy/sell
                        'amount_eur': Decimal(attrs['amount_fiat']),
                        'crypto_symbol': attrs.get('cryptocoin_id'),
                        'crypto_amount': Decimal(attrs['amount_cryptocoin']),
                        'price': Decimal(attrs['price']),
                    })

            return sorted(filtered_trades, key=lambda x: x['date'])

        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Trading-Historie: {e}")
            return []

    def calculate_portfolio_performance(self) -> Dict:
        """
        Berechnet Portfolio-Performance über Zeit

        Returns:
            Dict mit Performance-Daten für Chart
        """
        trades = self.get_trades_history()
        current_portfolio = self.get_portfolio_summary()

        # Konvertiere current_value zu Decimal für Berechnungen
        current_value_decimal = Decimal(str(current_portfolio['total_value']))

        # Gruppiere Trades nach Monat
        monthly_data = {}
        cumulative_invested = Decimal('0')

        for trade in trades:
            month_key = trade['date'].strftime('%Y-%m')

            if month_key not in monthly_data:
                monthly_data[month_key] = {
                    'date': trade['date'],
                    'invested': Decimal('0'),
                    'trades_count': 0,
                }

            # Nur Käufe zählen als Investment
            if trade['type'] == 'buy':
                monthly_data[month_key]['invested'] += trade['amount_eur']
                cumulative_invested += trade['amount_eur']

            monthly_data[month_key]['trades_count'] += 1

        # Sortiere nach Datum
        sorted_months = sorted(monthly_data.items(), key=lambda x: x[1]['date'])

        # Berechne kumulatives Investment
        cumulative = Decimal('0')
        performance_data = []

        for month_key, data in sorted_months:
            cumulative += data['invested']
            performance_data.append({
                'date': data['date'].strftime('%Y-%m'),
                'invested': float(cumulative),
                'current_value': float(current_value_decimal),
                'profit_loss': float(current_value_decimal - cumulative),
            })

        # Berechne finale Statistiken
        total_profit_loss = current_value_decimal - cumulative_invested
        total_profit_loss_percent = Decimal('0')

        if cumulative_invested > 0:
            total_profit_loss_percent = (total_profit_loss / cumulative_invested) * Decimal('100')

        return {
            'data': performance_data,
            'total_invested': float(cumulative_invested),
            'current_value': float(current_value_decimal),
            'total_profit_loss': float(total_profit_loss),
            'total_profit_loss_percent': float(total_profit_loss_percent),
        }