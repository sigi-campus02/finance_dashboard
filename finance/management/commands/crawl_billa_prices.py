"""Crawlt aktuelle Preise aus dem Billa-Onlineshop."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from finance.models import BillaFiliale, BillaPreisHistorie, BillaProdukt
from finance.services import BillaScraper, PriceDetails, ProductMatcher
from finance.services.product_matcher import MatchResult
from finance.utils.billa_helpers import (
    BillaProductCache,
    chunked,
    ensure_log_file,
    percentage_change,
    should_skip_category,
)

if TYPE_CHECKING:  # pragma: no cover - nur für Typing
    from finance.services.billa_scraper import ScrapedProduct

LOGGER = logging.getLogger("finance.billa_crawler")


class Command(BaseCommand):
    help = "Crawlt aktuelle Produktpreise von shop.billa.at"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50, help="Anzahl Produkte, die verarbeitet werden")
        parser.add_argument("--dry-run", action="store_true", help="Keine Datenbankänderungen durchführen")
        parser.add_argument(
            "--min-confidence",
            type=float,
            default=80.0,
            help="Minimale Matching-Confidence (0-100)",
        )
        parser.add_argument("--log-file", type=str, help="Optionaler Pfad für die Log-Datei")
        parser.add_argument(
            "--exclude-category",
            action="append",
            dest="exclude",
            help="Überkategorien, die ignoriert werden sollen (mehrfach möglich)",
        )
        parser.add_argument(
            "--include-category",
            action="append",
            dest="include",
            help="Überkategorien, die ausschließlich betrachtet werden",)
        parser.add_argument("--batch-size", type=int, default=10, help="Batch-Größe für das Crawling")
        parser.add_argument(
            "--filial-nr",
            type=str,
            default="1330",
            help="Filialnummer, für die Preise geladen werden",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=1.8,
            help="Minimale Verzögerung zwischen Requests (Sekunden)",
        )
        parser.add_argument(
            "--export-csv",
            type=str,
            help="Pfad zu einer CSV-Datei für die exportierten Preisupdates",
        )
        parser.add_argument(
            "--min-purchases",
            type=int,
            default=1,
            help="Nur Produkte mit mindestens so vielen Käufen berücksichtigen",
        )

    def handle(self, *args, **options):  # noqa: C901 - Funktional umfangreich
        self.dry_run: bool = options["dry_run"]
        self.min_confidence: float = options["min_confidence"]
        self.batch_size: int = options["batch_size"]
        self.limit: int = options["limit"]
        self.exclude = options.get("exclude")
        self.include = options.get("include")
        self.min_purchases = options["min_purchases"]

        log_path = ensure_log_file(options.get("log_file"))
        self.logger = self._configure_logging(log_path)
        self.logger.info("Starte Billa Price Crawl (Limit=%s, Dry-Run=%s)", self.limit, self.dry_run)
        self.stdout.write(f"Log-Datei: {log_path}")

        self.cache = BillaProductCache()
        self.matcher = ProductMatcher(min_score=self.min_confidence, logger=self.logger)
        self.scraper = BillaScraper(
            options.get("filial_nr"),
            min_delay=options["delay"],
            logger=self.logger,
        )

        self.filiale = self._load_filiale(options.get("filial_nr"))
        if self.filiale is None:
            self.logger.warning(
                "Filiale %s wurde nicht gefunden. Es wird ohne Filialbezug fortgefahren.",
                options.get("filial_nr"),
            )

        products = self._load_products()
        if not products:
            self.stdout.write(self.style.WARNING("Keine Produkte gefunden, die verarbeitet werden können."))
            return

        start_time = timezone.now()
        summary = {
            "processed": 0,
            "matched": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
            "confidence_total": 0.0,
        }

        export_rows: List[Dict[str, object]] = []

        total = len(products)
        self.stdout.write(f"Lade Top {total} Produkte...")

        for batch in chunked(products, self.batch_size):
            for produkt in batch:
                summary["processed"] += 1
                index = summary["processed"]
                self.stdout.write(f"Matching Produkt {index}/{total}: \"{produkt.name_normalisiert}\"")
                try:
                    result = self._process_product(produkt)
                except Exception as exc:  # pragma: no cover - defensive logging
                    summary["errors"] += 1
                    self.logger.exception("Fehler bei Produkt %s: %s", produkt.id, exc)
                    continue

                if result is None:
                    summary["skipped"] += 1
                    continue

                match, price_details, price_updated, old_price = result
                summary["matched"] += 1
                summary["confidence_total"] += match.score

                if price_details and price_updated:
                    summary["updated"] += 1
                    export_rows.append(
                        {
                            "produkt_id": produkt.id,
                            "produkt": produkt.name_normalisiert,
                            "neuer_preis": f"{price_details.price:.2f}",
                            "alte_preis": f"{old_price:.2f}" if old_price is not None else "-",
                            "menge": f"{price_details.quantity}",
                            "einheit": price_details.unit,
                            "match_score": f"{match.score:.1f}",
                            "match_quelle": match.product.source,
                            "dry_run": self.dry_run,
                        }
                    )

        self._export_csv(export_rows, options.get("export_csv"))

        duration = timezone.now() - start_time
        avg_confidence = (
            summary["confidence_total"] / summary["matched"] if summary["matched"] else 0
        )

        self._print_summary(summary, duration, avg_confidence)

        if not self.dry_run:
            self.cache.save()

        self.logger.info(
            "Summary: processed=%s matched=%s updated=%s skipped=%s errors=%s avg_confidence=%.1f duration=%s",
            summary["processed"],
            summary["matched"],
            summary["updated"],
            summary["skipped"],
            summary["errors"],
            avg_confidence,
            duration,
        )

    # ------------------------------------------------------------------
    def _process_product(self, produkt: BillaProdukt):
        if produkt.anzahl_kaeufe < self.min_purchases:
            self.logger.debug(
                "Produkt %s (%s) wegen geringer Kaufanzahl übersprungen",
                produkt.id,
                produkt.anzahl_kaeufe,
            )
            return None

        if should_skip_category(produkt.ueberkategorie, self.exclude):
            self.logger.debug(
                "Produkt %s (%s) wegen Kategorie %s übersprungen",
                produkt.id,
                produkt.name_normalisiert,
                produkt.ueberkategorie,
            )
            return None

        if self.include and produkt.ueberkategorie not in self.include:
            return None

        cached_match = self._match_from_cache(produkt)
        if cached_match:
            match = cached_match
            self.stdout.write(
                f"  → Cache-Treffer: {match.product.name} ({match.score:.0f}% confidence)"
            )
        else:
            match = self._match_via_search(produkt)

        if not match:
            self.logger.info("Kein passendes Produkt gefunden für %s", produkt.name_normalisiert)
            return None

        price_details = match.product.price_details
        if price_details is None and match.product.sku:
            detailed = self.scraper.fetch_by_sku(match.product.sku)
            if detailed:
                match = MatchResult(
                    product=detailed,
                    score=match.score,
                    score_components=match.score_components,
                    sanitized_candidate=match.sanitized_candidate,
                )
                price_details = detailed.price_details

        if price_details is None:
            self.logger.warning("Kein Preis für Produkt %s gefunden", match.product.name)
            return None

        price_updated, old_price = self._update_database(produkt, price_details)

        if price_updated:
            change_text = f" (vorher: €{old_price:.2f})" if old_price is not None else ""
            action_text = "Preis aktualisiert"
        else:
            change_text = "" if old_price is None else f" (unverändert: €{old_price:.2f})"
            action_text = "Preis geprüft"

        self.stdout.write(
            f"  → {action_text}: €{price_details.price:.2f}{change_text}"
        )
        self.logger.info(
            "%s – %s €%.2f (Score %.1f)",
            produkt.name_normalisiert,
            action_text,
            price_details.price,
            match.score,
        )

        if not self.dry_run:
            self.cache.set(produkt.id, match.url, match.sku, match.score)

        return match, price_details, price_updated, old_price

    # ------------------------------------------------------------------
    def _match_from_cache(self, produkt: BillaProdukt) -> Optional[MatchResult]:
        entry = self.cache.get(produkt.id)
        if not entry:
            return None

        candidate: Optional["ScrapedProduct"] = None
        if entry.url:
            candidate = self.scraper.fetch_by_url(entry.url)
        if candidate is None and entry.sku:
            candidate = self.scraper.fetch_by_sku(entry.sku)

        if candidate is None:
            return None

        match = self.matcher.score_cached_candidate(produkt.name_normalisiert, candidate)
        if match and match.score >= self.min_confidence:
            self.logger.debug(
                "Cache-Treffer für %s mit Score %.1f", produkt.name_normalisiert, match.score
            )
            return match
        return None

    # ------------------------------------------------------------------
    def _match_via_search(self, produkt: BillaProdukt) -> Optional[MatchResult]:
        candidates = self.scraper.search_products(produkt.name_normalisiert, limit=20)
        match = self.matcher.match(produkt.name_normalisiert, candidates)
        if match:
            message = f"  → Match gefunden: {match.product.name} ({match.score:.0f}% confidence)"
            self.stdout.write(message)
            self.logger.info("%s → %s", produkt.name_normalisiert, message.strip())
        else:
            self.stdout.write("  → Kein Match gefunden")
            self.logger.info("%s → Kein Match", produkt.name_normalisiert)
        return match

    # ------------------------------------------------------------------
    def _update_database(self, produkt: BillaProdukt, details: PriceDetails):
        old_price = produkt.letzter_preis
        price_changed = old_price is None or old_price != details.price

        if price_changed and old_price is not None:
            diff_pct = percentage_change(float(details.price), float(old_price))
            if diff_pct and abs(diff_pct) > 20:
                self.logger.warning(
                    "Preisänderung über 20%% für %s: alt %.2f, neu %.2f",
                    produkt.name_normalisiert,
                    old_price,
                    details.price,
                )

        if not self.dry_run:
            produkt.letzter_preis = details.price
            produkt.save(update_fields=["letzter_preis", "letzte_aktualisierung"])
            self._update_preishistorie(produkt, details)

        return price_changed, old_price

    # ------------------------------------------------------------------
    def _update_preishistorie(self, produkt: BillaProdukt, details) -> None:
        if self.filiale is None:
            self.logger.debug(
                "Preishistorie für %s übersprungen (keine Filiale definiert)",
                produkt.name_normalisiert,
            )
            return

        today = timezone.now().date()
        filters = {"produkt": produkt, "datum": today, "filiale": self.filiale}

        artikel_field = BillaPreisHistorie._meta.get_field("artikel")
        defaults = {
            "preis": details.price,
            "menge": details.quantity,
            "einheit": details.unit,
        }

        if self.filiale:
            defaults["filiale"] = self.filiale

        if artikel_field.null:
            defaults["artikel"] = None
        else:
            artikel = produkt.artikel.order_by("-einkauf__datum").first()
            if artikel is None:
                self.logger.warning(
                    "Keine Artikelreferenz für Preishistorie von %s gefunden", produkt.name_normalisiert
                )
                return
            defaults["artikel"] = artikel

        with transaction.atomic():
            historie, created = BillaPreisHistorie.objects.update_or_create(
                defaults=defaults,
                **filters,
            )
            if not created:
                historie.preis = details.price
                historie.menge = details.quantity
                historie.einheit = details.unit
                historie.save(update_fields=["preis", "menge", "einheit"])

    # ------------------------------------------------------------------
    def _load_products(self) -> List[BillaProdukt]:
        queryset = BillaProdukt.objects.filter(anzahl_kaeufe__gte=self.min_purchases)
        if self.exclude:
            queryset = queryset.exclude(ueberkategorie__in=self.exclude)
        if self.include:
            queryset = queryset.filter(ueberkategorie__in=self.include)
        return list(queryset.order_by("-anzahl_kaeufe")[: self.limit])

    # ------------------------------------------------------------------
    def _load_filiale(self, filial_nr: Optional[str]) -> Optional[BillaFiliale]:
        if not filial_nr:
            return None
        try:
            return BillaFiliale.objects.get(pk=filial_nr)
        except BillaFiliale.DoesNotExist:
            return None

    # ------------------------------------------------------------------
    def _configure_logging(self, log_path: Path) -> logging.Logger:
        logger = LOGGER
        logger.setLevel(logging.INFO)
        logger.handlers.clear()

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        stream_handler = logging.StreamHandler(self.stdout)

        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        file_handler.setFormatter(formatter)
        stream_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

        return logger

    # ------------------------------------------------------------------
    def _print_summary(self, summary: Dict[str, object], duration, avg_confidence: float) -> None:
        self.stdout.write("\n===== Billa Price Crawl Summary =====")
        self.stdout.write(f"Produkte verarbeitet: {summary['processed']}")
        self.stdout.write(f"Erfolgreiche Matches: {summary['matched']}")
        self.stdout.write(f"Preise aktualisiert: {summary['updated']}")
        self.stdout.write(f"Übersprungen: {summary['skipped']}")
        self.stdout.write(f"Fehler: {summary['errors']}")
        self.stdout.write(f"Durchschnittliche Matching-Confidence: {avg_confidence:.1f}%")
        self.stdout.write(f"Laufzeit: {duration}")

    # ------------------------------------------------------------------
    def _export_csv(self, rows: List[Dict[str, object]], export_path: Optional[str]) -> None:
        if not export_path:
            return
        path = Path(export_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "produkt_id",
                    "produkt",
                    "neuer_preis",
                    "alte_preis",
                    "menge",
                    "einheit",
                    "match_score",
                    "match_quelle",
                    "dry_run",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

        self.logger.info("Preis-Updates nach %s exportiert", path)
