"""Matching-Logik zwischen lokalen Produktnamen und Billa-Daten."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

try:  # pragma: no cover - RapidFuzz ist optional
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover - Fallback für Tests ohne RapidFuzz
    from difflib import SequenceMatcher

    class _FallbackFuzz:
        @staticmethod
        def token_set_ratio(a: str, b: str) -> float:
            return SequenceMatcher(None, a, b).ratio() * 100

        token_sort_ratio = token_set_ratio
        partial_ratio = token_set_ratio

    fuzz = _FallbackFuzz()

from finance.services.billa_scraper import ScrapedProduct
from finance.utils.billa_helpers import sanitize_product_name

LOGGER = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Ergebnis eines Matching-Versuchs."""

    product: ScrapedProduct
    score: float
    score_components: Dict[str, float]
    sanitized_candidate: str

    @property
    def name(self) -> str:
        return self.product.name

    @property
    def url(self) -> Optional[str]:
        return self.product.url

    @property
    def sku(self) -> Optional[str]:
        return self.product.sku


class ProductMatcher:
    """Findet das beste Matching für ein lokales Produkt."""

    def __init__(self, *, min_score: float = 75.0, logger: Optional[logging.Logger] = None) -> None:
        self.min_score = min_score
        self.logger = logger or LOGGER

    # ------------------------------------------------------------------
    def match(self, local_name: str, candidates: Sequence[ScrapedProduct]) -> Optional[MatchResult]:
        """Sucht den besten Treffer in der Kandidatenliste."""

        if not candidates:
            return None

        sanitized_local = sanitize_product_name(local_name)
        scored: List[MatchResult] = []

        for candidate in candidates:
            result = self._score_candidate(sanitized_local, candidate)
            if result:
                scored.append(result)

        if not scored:
            return None

        scored.sort(key=lambda item: item.score, reverse=True)
        best = scored[0]

        if best.score < self.min_score:
            self.logger.debug(
                "Bestes Match (%s) unterschreitet Schwellwert %.1f", best.product.name, self.min_score
            )
            return None

        return best

    # ------------------------------------------------------------------
    def score_cached_candidate(self, local_name: str, candidate: ScrapedProduct) -> Optional[MatchResult]:
        """Bewertet einen bereits bekannten Kandidaten."""

        sanitized_local = sanitize_product_name(local_name)
        return self._score_candidate(sanitized_local, candidate)

    # ------------------------------------------------------------------
    def _score_candidate(self, sanitized_local: str, candidate: ScrapedProduct) -> Optional[MatchResult]:
        sanitized_remote = sanitize_product_name(candidate.name)
        if not sanitized_remote:
            return None

        token_set = fuzz.token_set_ratio(sanitized_local, sanitized_remote)
        token_sort = fuzz.token_sort_ratio(sanitized_local, sanitized_remote)
        partial = fuzz.partial_ratio(sanitized_local, sanitized_remote)

        score = max(token_set, token_sort, partial)

        if sanitized_local in sanitized_remote or sanitized_remote in sanitized_local:
            score = max(score, 98)

        score = self._apply_numeric_bonus(sanitized_local, sanitized_remote, score)
        score = min(score, 100.0)

        score_components = {
            "token_set": float(token_set),
            "token_sort": float(token_sort),
            "partial": float(partial),
        }

        return MatchResult(
            product=candidate,
            score=float(score),
            score_components=score_components,
            sanitized_candidate=sanitized_remote,
        )

    @staticmethod
    def _apply_numeric_bonus(local: str, remote: str, score: float) -> float:
        """Verbessert die Bewertung, wenn numerische Angaben übereinstimmen."""

        local_numbers = re.findall(r"\d+[\.,]?\d*", local)
        remote_numbers = re.findall(r"\d+[\.,]?\d*", remote)
        if not local_numbers or not remote_numbers:
            return score

        matches = 0
        for number in local_numbers:
            number_normalized = number.replace(",", ".")
            if any(number_normalized == other.replace(",", ".") for other in remote_numbers):
                matches += 1

        if matches == len(local_numbers):
            return max(score, 95)
        if matches:
            return score + matches * 2
        return score
