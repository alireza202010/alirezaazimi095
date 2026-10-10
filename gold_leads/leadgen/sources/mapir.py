"""Map.ir (مپ) Search API — another Iranian map, used when Neshan search isn't available.

Key: from corp.map.ir (sent as the ``x-api-key`` header). ``POST https://map.ir/search/v2``
with ``{"text", "$select": "poi", "lat", "lon"}`` returns ``{"value": [...]}`` items with
title, address, city, region (often «منطقه ۶»), neighborhood and a GeoJSON ``geom``.
Results are biased to the given point, so we sweep a grid over Tehran like Neshan.
"""

from __future__ import annotations

import logging

from ..geo import TEHRAN, BBox, grid_points
from ..http import Http
from ..http_errors import is_auth_error
from ..models import Lead
from ..text import is_gold_related, normalize

log = logging.getLogger(__name__)

SEARCH_URL = "https://map.ir/search/v2"
DEFAULT_TERMS = ("طلا فروشی", "گالری طلا", "طلای آبشده", "سکه و طلا")


def parse_items(items: list[dict]) -> list[Lead]:
    leads = []
    for item in items:
        title = (item.get("title") or "").strip()
        if not title or not is_gold_related(title, item.get("type"), item.get("fclass")):
            continue
        coords = (item.get("geom") or {}).get("coordinates") or []
        if item.get("geom", {}).get("type") != "Point" or len(coords) < 2:
            continue
        lng, lat = float(coords[0]), float(coords[1])
        city = normalize(item.get("city"))
        if not TEHRAN.contains(lat, lng) or (city and city != "تهران"):
            continue
        address = item.get("address") or ""
        region = item.get("region") or ""
        leads.append(
            Lead(
                name=title,
                lat=lat,
                lng=lng,
                address=f"{address} ({region})" if region and region not in address else address,
                neighbourhood=item.get("neighborhood") or "",
                category=item.get("fclass") or item.get("type") or "",
                sources=["mapir"],
            )
        )
    return leads


class MapirSource:
    name = "mapir"

    def __init__(self, http: Http, api_key: str, terms=DEFAULT_TERMS, step: float = 0.02, bbox: BBox = TEHRAN):
        self.http = http
        self.api_key = api_key
        self.terms = terms
        self.step = step
        self.bbox = bbox

    def search(self, term: str, lat: float, lng: float) -> list[dict]:
        body = {"text": term, "$select": "poi", "lat": lat, "lon": lng}
        headers = {"x-api-key": self.api_key, "content-type": "application/json"}
        return self.http.post_json(SEARCH_URL, body, headers=headers).json().get("value", [])

    def collect(self) -> list[Lead]:
        points = grid_points(self.bbox, self.step)
        log.info("Map.ir: %d grid points x %d terms", len(points), len(self.terms))
        leads: list[Lead] = []
        for i, (lat, lng) in enumerate(points, 1):
            for term in self.terms:
                try:
                    items = self.search(term, lat, lng)
                except Exception as exc:
                    if is_auth_error(exc):
                        log.error("Map.ir rejected the key (%s); keeping %d results", exc, len(leads))
                        return leads
                    log.warning("Map.ir search failed at %s,%s (%s): %s", lat, lng, term, exc)
                    continue
                leads.extend(parse_items(items))
            if i % 25 == 0:
                log.info("Map.ir: %d/%d points, %d raw results", i, len(points), len(leads))
        return leads
