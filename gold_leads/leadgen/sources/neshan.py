"""Neshan (نشان) Search API — Iranian map with very good coverage of Tehran shops.

Key: a *service* key (``service.…``) from platform.neshan.org. In Neshan's own MCP server
search and reverse geocoding share one key group, so a key created for
«تبدیل نقطه به آدرس» may already allow search — ``python -m leadgen check`` tells you.

Current endpoint is ``/v3/search`` (``q`` = JSON with term, center and bound); the older
``/v1/search`` (term, lat, lng) is tried as a fallback. Each call returns the places
around one point, so we sweep a grid over Tehran and bound every call to its grid cell.
No phone numbers here — phones come from Google/OSM or the Claude enrichment step.
"""

from __future__ import annotations

import json
import logging

from ..geo import TEHRAN, BBox, grid_points, mercator_to_wgs84
from ..http import Http
from ..http_errors import is_auth_error, status_of
from ..models import Lead
from ..text import is_gold_related

log = logging.getLogger(__name__)

SEARCH_V3_URL = "https://api.neshan.org/v3/search"
SEARCH_V1_URL = "https://api.neshan.org/v1/search"
DEFAULT_TERMS = ("طلا فروشی", "گالری طلا", "جواهری", "طلای آبشده", "سکه و طلا")


class NeshanAccessError(RuntimeError):
    """The key is valid for some services but not for search (HTTP 401/403 on every search endpoint)."""


def item_point(item: dict) -> tuple[float, float] | None:
    """(lat, lng) from a search item; handles {x,y} in degrees or Web Mercator and {latitude,longitude}."""
    loc = item.get("location") or {}
    for lat, lng in ((loc.get("y"), loc.get("x")), (loc.get("latitude"), loc.get("longitude")),
                     (item.get("lat"), item.get("lng"))):
        try:
            lat, lng = float(lat), float(lng)
        except (TypeError, ValueError):
            continue
        if abs(lng) > 180 or abs(lat) > 90:
            lat, lng = mercator_to_wgs84(lng, lat)
        return lat, lng
    return None


def parse_items(items: list[dict]) -> list[Lead]:
    leads = []
    for item in items:
        title = (item.get("title") or "").strip()
        if not title or not is_gold_related(title, item.get("category"), item.get("type")):
            continue
        point = item_point(item)
        if point is None or not TEHRAN.contains(*point):
            continue
        address = item.get("address") or ""
        region = item.get("region") or ""
        leads.append(
            Lead(
                name=title,
                lat=point[0],
                lng=point[1],
                address=f"{address} ({region})" if region and region not in address else address,
                neighbourhood=item.get("neighbourhood") or item.get("neighborhood") or "",
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
        self.version: str | None = None  # "v3" or "v1" once detected

    def _call(self, version: str, term: str, lat: float, lng: float) -> list[dict]:
        headers = {"Api-Key": self.api_key}
        if version == "v3":
            half = self.step / 2
            payload = {
                "term": term,
                "center": {"latitude": lat, "longitude": lng},
                "bound": {
                    "southWest": {"latitude": lat - half, "longitude": lng - half},
                    "northEast": {"latitude": lat + half, "longitude": lng + half},
                },
            }
            params = {"q": json.dumps(payload, ensure_ascii=False)}
            return self.http.get(SEARCH_V3_URL, params=params, headers=headers).json().get("items", [])
        params = {"term": term, "lat": lat, "lng": lng}
        return self.http.get(SEARCH_V1_URL, params=params, headers=headers).json().get("items", [])

    def detect_version(self, lat: float = 35.6745, lng: float = 51.4210, term: str = DEFAULT_TERMS[0]) -> str:
        """Find a search endpoint this key may use; raises NeshanAccessError if none."""
        errors = []
        for version in ("v3", "v1"):
            try:
                self._call(version, term, lat, lng)
            except Exception as exc:
                errors.append(f"{version}: HTTP {status_of(exc) or exc}")
                if not is_auth_error(exc) and status_of(exc) not in (400, 404, 405):
                    raise  # network trouble etc. — not a question of access
                continue
            self.version = version
            return version
        raise NeshanAccessError(
            "This Neshan key cannot use the Search API (" + ", ".join(errors) + "). "
            "Enable search for the key in platform.neshan.org, or run without the neshan source."
        )

    def collect(self) -> list[Lead]:
        points = grid_points(self.bbox, self.step)
        version = self.version or self.detect_version(*points[len(points) // 2])
        log.info("Neshan %s search: %d grid points x %d terms", version, len(points), len(self.terms))
        leads: list[Lead] = []
        for i, (lat, lng) in enumerate(points, 1):
            for term in self.terms:
                try:
                    items = self._call(version, term, lat, lng)
                except Exception as exc:
                    if is_auth_error(exc):  # quota used up or key revoked mid-run
                        log.error("Neshan stopped accepting the key (%s); keeping %d results", exc, len(leads))
                        return leads
                    log.warning("Neshan search failed at %s,%s (%s): %s", lat, lng, term, exc)
                    continue
                leads.extend(parse_items(items))
            if i % 25 == 0:
                log.info("Neshan: %d/%d points, %d raw results", i, len(points), len(leads))
        return leads
