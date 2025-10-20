# finance/bitpanda_service.py
import requests
from decimal import Decimal
from typing import Dict, List, Optional
import logging
import os

logger = logging.getLogger(__name__)


class BitpandaService:
    """
    Service-Klasse für Bitpanda API Integration
    Nutzt BITPANDA_API_KEY aus Environment Variables
    """

    BASE_URL = 'https://api.bitpanda.com/v1'

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialisiert den Service mit einem API-Key

        Args:
            api_key: Optional Bitpanda API Key, falls None wird ENV Variable verwendet
        """
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
        """
        Führt API-Anfrage durch

        Args:
            endpoint: API Endpoint (z.B. '/wallets')
            method: HTTP Methode
            params: Query Parameter

        Returns:
            API Response als Dictionary

        Raises:
            requests.exceptions.RequestException: Bei API-Fehlern
        """
        url = f"{self.BASE_URL}{endpoint}"

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error("Bitpanda API: Ungültiger API-Key")
                raise ValueError("Ungültiger Bitpanda API-Key")
            elif e.response.status_code == 500:
                logger.error("Bitpanda API: Server-Fehler")
                raise ConnectionError("Bitpanda API Server-Fehler")
            else:
                logger.error(f"Bitpanda API Error: {e}")
                raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Bitpanda API Request fehlgeschlagen: {e}")
            raise

    def get_crypto_wallets(self) -> List[Dict]:
        """Holt alle Krypto-Wallets"""
        try:
            response = self._make_request('/wallets')
            return response.get('data', [])
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Crypto-Wallets: {e}")
            return []

    def get_fiat_wallets(self) -> List[Dict]:
        """Holt alle Fiat-Wallets"""
        try:
            response = self._make_request('/fiatwallets')
            return response.get('data', [])
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Fiat-Wallets: {e}")
            return []

    def get_asset_wallets(self) -> Dict:
        """Holt alle Asset-Wallets (Crypto, Commodities)"""
        try:
            response = self._make_request('/asset-wallets')
            return response.get('data', {}).get('attributes', {})
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Asset-Wallets: {e}")
            return {}

    def get_trades(self, page_size: int = 50, trade_type: Optional[str] = None) -> List[Dict]:
        """Holt Trading-Historie"""
        params = {'page_size': page_size}
        if trade_type:
            params['type'] = trade_type

        try:
            response = self._make_request('/trades', params=params)
            return response.get('data', [])
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Trades: {e}")
            return []

    def get_fiat_transactions(self, page_size: int = 50,
                              transaction_type: Optional[str] = None,
                              status: Optional[str] = None) -> List[Dict]:
        """Holt Fiat-Transaktionen"""
        params = {'page_size': page_size}
        if transaction_type:
            params['type'] = transaction_type
        if status:
            params['status'] = status

        try:
            response = self._make_request('/fiatwallets/transactions', params=params)
            return response.get('data', [])
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Fiat-Transaktionen: {e}")
            return []

    def get_crypto_transactions(self, page_size: int = 50,
                                transaction_type: Optional[str] = None,
                                status: Optional[str] = None) -> List[Dict]:
        """Holt Crypto-Transaktionen"""
        params = {'page_size': page_size}
        if transaction_type:
            params['type'] = transaction_type
        if status:
            params['status'] = status

        try:
            response = self._make_request('/wallets/transactions', params=params)
            return response.get('data', [])
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Crypto-Transaktionen: {e}")
            return []

    def get_portfolio_summary(self) -> Dict:
        """
        Erstellt eine Portfolio-Zusammenfassung

        Returns:
            Dictionary mit Portfolio-Daten
        """
        try:
            crypto_wallets = self.get_crypto_wallets()
            fiat_wallets = self.get_fiat_wallets()
            asset_wallets = self.get_asset_wallets()

            # Berechne Gesamt-Fiat-Wert
            total_fiat_eur = Decimal('0')
            for wallet in fiat_wallets:
                attrs = wallet.get('attributes', {})
                balance = Decimal(attrs.get('balance', '0'))
                symbol = attrs.get('fiat_symbol', '')

                if symbol == 'EUR':
                    total_fiat_eur += balance

            return {
                'crypto_wallets': crypto_wallets,
                'fiat_wallets': fiat_wallets,
                'asset_wallets': asset_wallets,
                'total_fiat_eur': float(total_fiat_eur),
                'crypto_count': len([w for w in crypto_wallets if not w.get('attributes', {}).get('deleted', False)]),
                'fiat_count': len(fiat_wallets),
            }
        except Exception as e:
            logger.error(f"Fehler beim Erstellen der Portfolio-Zusammenfassung: {e}")
            return {}