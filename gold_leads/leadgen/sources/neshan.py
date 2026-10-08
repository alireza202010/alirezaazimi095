"""Neshan (نشان) Search API — Iranian map with very good coverage of Tehran shops.

Docs: https://platform.neshan.org/api/search  (free API key from platform.neshan.org).
Returns up to ~30 places around a point per term, so we sweep a grid over Tehran.
No phone numbers here — phones come from Google/OSM or the Claude enrichment step.
"""

from __future__ import annotations

import logging

from ..geo import TEHRAN, BBox, grid_points
from ..http import Http
from ..models import Lead
from ..text import is_gold_related

log = logging.getLogger(__name__)

SEARCH_URL = "https://api.neshan.org/v1/search"
DEFAULT_TERMS = ("طلا فروشی", "گالری طلا", "جواهری", "طلای آبشده", "سکه و طلا")


def parse_items(items: list[dict]) -> list[Lead]:
    leads = []
    for item in items:
        title = (item.get("title") or "").strip()
        if not title or not is_gold_related(title, item.get("category"), item.get("type")):
            continue
        loc = item.get("location") or {}
        try:
            lat, lng = float(loc["y"]), float(loc["x"])
        except (KeyError, TypeError, ValueError):
            continue
        if not TEHRAN.contains(lat, lng):
            continue
        address = item.get("address") or ""
        region = item.get("region") or ""
        leads.append(
            Lead(
                name=title,
                lat=lat,
                lng=lng,
                address=f"{address} ({region})" if region and region not in address else address,
                neighbourhood=item.get("neighbourhood") or "",
                category=item.get("category") or item.get("type") or "",
                sources=["neshan"],
            )
        )
    return leads


class NeshanSource:
    name = "neshan"

    def __init__(self, http: Http, api_key: str, terms=DEFAULT_TERMS, step: float = 0.02, bbox: BBox = TEHRAN):
        self.http = http
        self.api_key = api_key
        self.terms = terms
        self.step = step
        self.bbox = bbox

    def collect(self) -> list[Lead]:
        points = grid_points(self.bbox, self.step)
        log.info("Neshan: %d grid points x %d terms", len(points), len(self.terms))
        leads: list[Lead] = []
        for i, (lat, lng) in enumerate(points, 1):
            for term in self.terms:
                try:
                    resp = self.http.get(
                        SEARCH_URL,
                        params={"term": term, "lat": lat, "lng": lng},
                        headers={"Api-Key": self.api_key},
                    )
                except Exception as exc:
                    log.warning("Neshan search failed at %s,%s (%s): %s", lat, lng, term, exc)
                    continue
                leads.extend(parse_items(resp.json().get("items", [])))
            if i % 25 == 0:
                log.info("Neshan: %d/%d points, %d raw results", i, len(points), len(leads))
        return leads
