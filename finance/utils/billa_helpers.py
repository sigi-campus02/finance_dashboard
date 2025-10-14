"""Helper-Funktionen für den Billa Price Crawler."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Iterator, Optional, Sequence, TypeVar

from django.conf import settings

LOGGER = logging.getLogger(__name__)

_SANITIZE_PATTERN = re.compile(r"[^a-z0-9]+", re.IGNORECASE)
_UNIT_REPLACEMENTS = {
    "ltr": "l",
    "lt": "l",
    "liter": "l",
    "liters": "l",
    "kilogramm": "kg",
    "kilogram": "kg",
    "gramm": "g",
    "grams": "g",
    "stk": "stueck",
    "stück": "stueck",
}

T = TypeVar("T")


def sanitize_product_name(name: str) -> str:
    """Normalisiert Produktnamen für zuverlässiges Matching."""

    if not name:
        return ""

    lower = name.lower()
    for search, repl in _UNIT_REPLACEMENTS.items():
        lower = lower.replace(search, repl)
    return _SANITIZE_PATTERN.sub(" ", lower).strip()


def normalize_unit(unit: Optional[str]) -> Optional[str]:
    """Normalisiert Einheitenbezeichnungen."""

    if unit is None:
        return None
    normalized = unit.lower().strip()
    return _UNIT_REPLACEMENTS.get(normalized, normalized)


class RateLimiter:
    """Einfache Rate-Limitierung zwischen Requests."""

    def __init__(self, min_delay_seconds: float = 1.5):
        self.min_delay_seconds = max(min_delay_seconds, 0)
        self._last_call: Optional[float] = None

    def wait(self) -> None:
        now = time.monotonic()
        if self._last_call is not None:
            elapsed = now - self._last_call
            if elapsed < self.min_delay_seconds:
                time.sleep(self.min_delay_seconds - elapsed)
        self._last_call = time.monotonic()


def chunked(sequence: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    """Teilt eine Sequenz in gleich große Batches."""

    if size <= 0:
        raise ValueError("Batch size must be > 0")
    for start in range(0, len(sequence), size):
        yield sequence[start : start + size]


def ensure_log_file(path: Optional[str]) -> Path:
    """Erstellt falls nötig das Verzeichnis für die Log-Datei."""

    if path:
        log_path = Path(path)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = Path(settings.BASE_DIR) / "logs"
        log_path = log_dir / f"billa_price_crawler_{timestamp}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return log_path


@dataclass
class CacheEntry:
    """Repräsentiert eine gecachte Produktinformation."""

    produkt_id: int
    url: Optional[str]
    sku: Optional[str]
    last_score: Optional[float]
    updated_at: str

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "produkt_id": self.produkt_id,
            "url": self.url,
            "sku": self.sku,
            "last_score": self.last_score,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Optional[str]]) -> "CacheEntry":
        return cls(
            produkt_id=int(data["produkt_id"]),
            url=data.get("url"),
            sku=data.get("sku"),
            last_score=data.get("last_score"),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
        )


class BillaProductCache:
    """Persistenter Cache für gematchte Billa-Produkt-URLs."""

    def __init__(self, path: Optional[Path] = None):
        if path is None:
            data_dir = Path(settings.BASE_DIR) / "data"
            path = data_dir / "billa_product_cache.json"
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: Dict[str, CacheEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            LOGGER.warning("Konnte Cache-Datei %s nicht laden: %s", self.path, exc)
            return
        for key, value in raw.items():
            try:
                self._entries[key] = CacheEntry.from_dict(value)
            except (KeyError, TypeError, ValueError) as exc:
                LOGGER.debug("Überspringe invalide Cache-Zeile %s: %s", key, exc)

    def get(self, produkt_id: int) -> Optional[CacheEntry]:
        return self._entries.get(str(produkt_id))

    def set(self, produkt_id: int, url: Optional[str], sku: Optional[str], score: Optional[float]) -> None:
        entry = CacheEntry(
            produkt_id=produkt_id,
            url=url,
            sku=sku,
            last_score=score,
            updated_at=datetime.utcnow().isoformat(),
        )
        self._entries[str(produkt_id)] = entry

    def save(self) -> None:
        payload = {key: entry.to_dict() for key, entry in self._entries.items()}
        try:
            with self.path.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
        except OSError as exc:
            LOGGER.error("Konnte Cache-Datei %s nicht schreiben: %s", self.path, exc)


def should_skip_category(category: Optional[str], blacklist: Optional[Iterable[str]]) -> bool:
    """Prüft, ob eine Kategorie ignoriert werden soll."""

    if not blacklist:
        return False
    if not category:
        return False
    normalized = category.lower()
    return any(item.lower() == normalized for item in blacklist)


def percentage_change(new: float, old: float) -> Optional[float]:
    """Berechnet die prozentuale Veränderung."""

    if old in (0, None):
        return None
    try:
        return (new - old) / old * 100
    except ZeroDivisionError:
        return None
