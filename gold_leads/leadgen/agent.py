"""The lead agent: collect -> filter -> dedupe -> districts -> enrich -> score -> sheet."""

from __future__ import annotations

import datetime as dt
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import export
from .dedupe import dedupe
from .districts import DistrictResolver, fetch_osm_district_polygons, load_polygons, save_polygons
from .geo import TEHRAN
from .http import Http
from .models import Lead
from .scoring import score_all
from .sources import GooglePlacesSource, NeshanSource, OsmSource
from .table import ALL_TAB, build_tabs

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    sources: list[str] = field(default_factory=lambda: ["google", "neshan", "osm"])
    neshan_key: str = ""
    google_key: str = ""
    sheet_id: str = ""
    service_account_file: str = ""
    enrich: bool = False
    enrich_limit: int = 50
    enrich_refresh: bool = False
    enrich_model: str = "claude-opus-5-5"
    enrich_effort: str = "medium"
    enrich_workers: int = 4
    business_context: str = ""
    grid_step: float = 0.02
    districts_file: Path = ROOT / "cache" / "tehran_districts.json"
    cache_dir: Path = ROOT / "cache"
    out_dir: Path = ROOT / "output"
    http_delay: float = 0.2

    @classmethod
    def from_env(cls, **overrides) -> "Config":
        cfg = cls(
            neshan_key=os.getenv("NESHAN_API_KEY", ""),
            google_key=os.getenv("GOOGLE_MAPS_API_KEY", ""),
            sheet_id=os.getenv("GOOGLE_SHEET_ID", ""),
            service_account_file=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", ""),
            business_context=os.getenv("BUSINESS_CONTEXT", ""),
        )
        for key, value in overrides.items():
            if value is not None:
                setattr(cfg, key, value)
        return cfg


class LeadAgent:
    def __init__(self, config: Config, http: Http | None = None, enricher=None, sheet=None):
        self.cfg = config
        self.http = http or Http(delay=config.http_delay)
        self._enricher = enricher
        self._sheet = sheet

    # ---------------------------------------------------------------- steps
    def build_sources(self) -> list:
        sources = []
        for name in self.cfg.sources:
            if name == "google":
                if not self.cfg.google_key:
                    log.warning("Skipping Google Places: GOOGLE_MAPS_API_KEY is not set")
                    continue
                sources.append(GooglePlacesSource(self.http, self.cfg.google_key))
            elif name == "neshan":
                if not self.cfg.neshan_key:
                    log.warning("Skipping Neshan: NESHAN_API_KEY is not set")
                    continue
                sources.append(NeshanSource(self.http, self.cfg.neshan_key, step=self.cfg.grid_step))
            elif name == "osm":
                sources.append(OsmSource(self.http))
            else:
                raise ValueError(f"Unknown source: {name}")
        if not sources:
            raise SystemExit("No data source available — set GOOGLE_MAPS_API_KEY and/or NESHAN_API_KEY, or use --sources osm")
        return sources

    def collect(self) -> list[Lead]:
        leads: list[Lead] = []
        for source in self.build_sources():
            try:
                found = source.collect()
            except Exception as exc:
                log.error("Source %s failed: %s", source.name, exc)
                continue
            log.info("%s: %d raw results", source.name, len(found))
            leads.extend(found)
        return [l for l in leads if l.lat is None or TEHRAN.contains(l.lat, l.lng)]

    def resolver(self) -> DistrictResolver:
        polygons = load_polygons(self.cfg.districts_file)
        return DistrictResolver(
            http=self.http,
            neshan_key=self.cfg.neshan_key,
            polygons=polygons,
            cache_file=self.cfg.cache_dir / "neshan_reverse.json",
        )

    def enricher(self):
        if self._enricher is None:
            from .enrich import Enricher

            self._enricher = Enricher(
                model=self.cfg.enrich_model,
                effort=self.cfg.enrich_effort,
                business_context=self.cfg.business_context,
                workers=self.cfg.enrich_workers,
                cache_file=self.cfg.cache_dir / "enrichment.json",
            )
        return self._enricher

    def sheet(self):
        if self._sheet is None and self.cfg.sheet_id:
            from .sheets import SheetSync

            self._sheet = SheetSync(self.cfg.sheet_id, self.cfg.service_account_file)
        return self._sheet

    # ---------------------------------------------------------------- run
    def run(self) -> dict:
        today = dt.date.today().isoformat()
        raw = self.collect()
        if not raw:
            raise SystemExit("No shops found (all sources failed or returned nothing) — sheet left untouched.")
        leads = dedupe(raw)
        log.info("%d raw results -> %d unique shops", len(raw), len(leads))

        self.resolver().resolve_all(leads)
        enriched = 0
        if self.cfg.enrich:
            enriched = self.enricher().enrich(leads, limit=self.cfg.enrich_limit, refresh=self.cfg.enrich_refresh)
        score_all(leads)

        xlsx = self.cfg.out_dir / "tehran_gold_leads.xlsx"
        sheet = self.sheet()
        existing = sheet.read_tabs() if sheet else export.read_xlsx(xlsx)
        tabs = build_tabs(leads, existing, today)
        export.write_xlsx(tabs, xlsx)
        export.write_csv(tabs, self.cfg.out_dir / "tehran_gold_leads.csv")
        url = sheet.write_tabs(tabs) if sheet else ""

        districts = {l.district for l in leads if l.district}
        return {
            "raw_results": len(raw),
            "unique_shops": len(leads),
            "rows_in_sheet": len(tabs[ALL_TAB]) - 1,
            "with_phone": sum(bool(l.phones) for l in leads),
            "with_mobile": sum(bool(l.mobiles) for l in leads),
            "districts_covered": len(districts),
            "unknown_district": sum(l.district is None for l in leads),
            "enriched": enriched,
            "xlsx": str(xlsx),
            "sheet_url": url,
        }

    def download_district_polygons(self) -> int:
        polygons = fetch_osm_district_polygons(self.http)
        save_polygons(polygons, self.cfg.districts_file)
        return len(polygons)
