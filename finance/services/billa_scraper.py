"""High-level scraper für shop.billa.at."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from finance.utils.billa_helpers import RateLimiter, normalize_unit

LOGGER = logging.getLogger(__name__)


@dataclass
class PriceDetails:
    """Preisdetails eines Produkts."""

    price: Decimal
    quantity: Decimal
    unit: str
    base_price: Optional[Decimal] = None
    base_unit: Optional[str] = None
    promotion: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


@dataclass
class ScrapedProduct:
    """Produktinformationen aus dem Webshop."""

    name: str
    url: Optional[str]
    sku: Optional[str]
    price_details: Optional[PriceDetails]
    source: str
    raw: Dict[str, Any]


class BillaScraper:
    """Kapselt alle HTTP-Aufrufe und das Parsen der Billa-Webseite."""

    BASE_URL = "https://shop.billa.at"
    SEARCH_ENDPOINT = "/api/search/full"
    PRODUCT_ENDPOINT = "/api/products/{sku}"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "de-AT,de;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }

    def __init__(
        self,
        filial_nr: Optional[str] = None,
        *,
        min_delay: float = 1.5,
        max_retries: int = 3,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)
        self.filial_nr = filial_nr
        self.logger = logger or LOGGER
        self.rate_limiter = RateLimiter(min_delay_seconds=min_delay)
        self.max_retries = max(1, max_retries)
        self._robots_allowed: Optional[bool] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def search_products(self, query: str, *, limit: int = 20) -> List[ScrapedProduct]:
        """Durchsucht den Onlineshop nach einem Produkt."""

        if not self._is_allowed():
            self.logger.warning("Robots.txt verbietet das Crawlen der Such-API")
            return []

        params = {
            "searchTerm": query,
            "page": 1,
            "pageSize": limit,
            "sorting": "relevance",
        }
        if self.filial_nr:
            params["branchId"] = self.filial_nr

        response = self._request("GET", f"{self.BASE_URL}{self.SEARCH_ENDPOINT}", params=params)
        if response is None:
            return []

        try:
            payload = response.json()
        except json.JSONDecodeError:
            self.logger.error("Suche lieferte kein gültiges JSON (Status %s)", response.status_code)
            return []

        return self._parse_search_payload(payload)

    def fetch_by_sku(self, sku: str) -> Optional[ScrapedProduct]:
        """Lädt detaillierte Produktdaten über die API."""

        if not sku:
            return None

        if not self._is_allowed():
            self.logger.warning("Robots.txt verbietet das Crawlen der Produkt-API")
            return None

        url = f"{self.BASE_URL}{self.PRODUCT_ENDPOINT.format(sku=sku)}"
        response = self._request("GET", url)
        if response is None:
            return None

        try:
            payload = response.json()
        except json.JSONDecodeError:
            self.logger.error("Produkt-API lieferte kein gültiges JSON für %s", sku)
            return None

        name = payload.get("name") or payload.get("title")
        price_details = self._extract_price_details(payload)
        link = payload.get("productUrl") or payload.get("url")

        return ScrapedProduct(
            name=name or sku,
            url=self._absolute_url(link),
            sku=sku,
            price_details=price_details,
            source="api",
            raw=payload,
        )

    def fetch_by_url(self, url: str) -> Optional[ScrapedProduct]:
        """Parst eine Produktseite via HTML."""

        if not url:
            return None

        absolute_url = self._absolute_url(url)
        if absolute_url is None:
            return None

        response = self._request("GET", absolute_url, expect_json=False)
        if response is None:
            return None

        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        structured = soup.find("script", attrs={"type": "application/ld+json"})
        payload: Dict[str, Any] = {}
        if structured and structured.string:
            try:
                payload = json.loads(structured.string)
            except json.JSONDecodeError:
                self.logger.debug("Konnte ld+json nicht parsen für %s", absolute_url)

        name = payload.get("name") or soup.find("h1")
        if hasattr(name, "get_text"):
            name = name.get_text(strip=True)

        price_details = self._extract_price_from_html(payload, soup)

        return ScrapedProduct(
            name=name or absolute_url,
            url=absolute_url,
            sku=payload.get("sku") or payload.get("gtin13"),
            price_details=price_details,
            source="html",
            raw=payload or {"html_title": soup.title.string if soup.title else None},
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        expect_json: bool = True,
    ) -> Optional[requests.Response]:
        """Sendet einen HTTP-Request mit Retry-Logik."""

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            self.rate_limiter.wait()
            try:
                headers: Dict[str, str] = {}
                if not expect_json:
                    headers["Accept"] = "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"
                response = self.session.request(
                    method,
                    url,
                    params=params,
                    timeout=20,
                    headers=headers or None,
                )
                if response.status_code == 429:
                    self.logger.warning("Rate limit erreicht (%s). Warte und versuche erneut.", url)
                    time.sleep(3 * attempt)
                    continue
                if response.status_code >= 500:
                    self.logger.warning("Serverfehler %s bei %s", response.status_code, url)
                    time.sleep(attempt)
                    continue
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                self.logger.warning(
                    "Request-Fehler (%s Versuch %s/%s): %s",
                    url,
                    attempt,
                    self.max_retries,
                    exc,
                )
                time.sleep(attempt)
        if last_error:
            self.logger.error("Abbruch nach %s Versuchen für %s: %s", self.max_retries, url, last_error)
        return None

    def _parse_search_payload(self, payload: Dict[str, Any]) -> List[ScrapedProduct]:
        products: List[ScrapedProduct] = []
        items = (
            payload.get("products")
            or payload.get("productView")
            or payload.get("results")
            or []
        )
        for item in items:
            name = item.get("name") or item.get("title")
            if not name:
                continue
            price_details = self._extract_price_details(item)
            link = (
                item.get("productUrl")
                or item.get("url")
                or item.get("link")
                or item.get("seoUrl")
            )
            products.append(
                ScrapedProduct(
                    name=name,
                    url=self._absolute_url(link),
                    sku=item.get("sku") or item.get("id") or item.get("gtin"),
                    price_details=price_details,
                    source="search",
                    raw=item,
                )
            )
        return products

    def _extract_price_details(self, payload: Dict[str, Any]) -> Optional[PriceDetails]:
        price_info = payload.get("price") or payload.get("currentPrice") or payload.get("pricing")
        if isinstance(price_info, dict):
            value = price_info.get("value") or price_info.get("amount") or price_info.get("price")
            currency = price_info.get("currency")
            unit = price_info.get("salesUnit") or price_info.get("unit")
            quantity = price_info.get("amount") or price_info.get("quantity") or 1
            base = price_info.get("basePrice") or price_info.get("referencePrice")
            base_value = None
            base_unit = None
            if isinstance(base, dict):
                base_value = base.get("value") or base.get("amount")
                base_unit = base.get("unit")
            elif isinstance(base, (int, float, str)):
                try:
                    base_value = Decimal(str(base))
                except Exception:  # pragma: no cover - defensive programming
                    base_value = None
            promotion = None
            if "promotions" in payload:
                promos = payload.get("promotions")
                if isinstance(promos, list) and promos:
                    promo = promos[0]
                    if isinstance(promo, dict):
                        promotion = promo.get("name") or promo.get("label")
                    elif isinstance(promo, str):
                        promotion = promo
            try:
                price_value = Decimal(str(value))
                quantity_value = Decimal(str(quantity))
            except (TypeError, ValueError):
                return None
            unit = normalize_unit(unit) or "stk"
            if base_value is not None:
                try:
                    base_value = Decimal(str(base_value))
                except (TypeError, ValueError):
                    base_value = None
            if base_unit:
                base_unit = normalize_unit(base_unit)
            return PriceDetails(
                price=price_value,
                quantity=quantity_value if quantity_value > 0 else Decimal("1"),
                unit=unit,
                base_price=base_value,
                base_unit=base_unit,
                promotion=promotion,
                raw=price_info,
            )
        if isinstance(price_info, (int, float, str)):
            try:
                value = Decimal(str(price_info))
            except (TypeError, ValueError):
                return None
            return PriceDetails(
                price=value,
                quantity=Decimal("1"),
                unit="stk",
                raw={"value": price_info},
            )
        return None

    def _extract_price_from_html(self, payload: Dict[str, Any], soup: BeautifulSoup) -> Optional[PriceDetails]:
        if payload:
            offer = payload.get("offers")
            if isinstance(offer, dict):
                price = offer.get("price") or offer.get("priceSpecification", {}).get("price")
                unit = offer.get("unitCode")
                quantity = offer.get("priceSpecification", {}).get("priceQuantity", 1)
                try:
                    price_value = Decimal(str(price))
                    quantity_value = Decimal(str(quantity))
                except (TypeError, ValueError):
                    price_value = None
                if price_value is not None:
                    return PriceDetails(
                        price=price_value,
                        quantity=quantity_value if quantity_value and quantity_value > 0 else Decimal("1"),
                        unit=normalize_unit(unit) or "stk",
                        raw=offer,
                    )
        price_span = soup.select_one("[data-test='product-price']")
        if price_span and price_span.get_text(strip=True):
            text = price_span.get_text(strip=True)
            digits = text.replace("€", "").replace(" ", "").replace(",", ".")
            try:
                price_value = Decimal(digits)
            except (TypeError, ValueError, InvalidOperation):  # type: ignore[name-defined]
                price_value = None
            if price_value is not None:
                return PriceDetails(
                    price=price_value,
                    quantity=Decimal("1"),
                    unit="stk",
                    raw={"text": text},
                )
        return None

    def _absolute_url(self, url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        if url.startswith("http"):
            return url
        return f"{self.BASE_URL}{url}"

    def _is_allowed(self) -> bool:
        if self._robots_allowed is not None:
            return self._robots_allowed
        try:
            response = self.session.get(f"{self.BASE_URL}/robots.txt", timeout=10)
            response.raise_for_status()
            disallow_lines = [line.strip() for line in response.text.splitlines() if line.lower().startswith("disallow")] \
                if response.text else []
            for line in disallow_lines:
                if "/api" in line or "*" == line.partition(":")[2].strip():
                    self._robots_allowed = False
                    break
            else:
                self._robots_allowed = True
        except requests.RequestException:
            self._robots_allowed = True
        return bool(self._robots_allowed)
