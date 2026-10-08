"""Assign each lead to one of Tehran's 22 municipal districts (مناطق ۲۲گانه).

Resolution order (first hit wins, the winner is recorded in ``lead.district_source``):
1. ``neshan``       – Neshan reverse geocoding returns ``municipality_zone`` (most accurate).
2. ``polygon``      – point-in-polygon against district boundaries (OSM download or your GeoJSON).
3. ``address``      – the address text explicitly says «منطقه ۶».
4. ``neighbourhood``– well-known neighbourhood names from ``data/neighbourhoods.json``.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .geo import TEHRAN, Segment, point_in_segments, ring_to_segments
from .http import Http
from .models import Lead
from .text import normalize, to_latin_digits

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
NEIGHBOURHOODS_FILE = DATA_DIR / "neighbourhoods.json"

NESHAN_REVERSE_URL = "https://api.neshan.org/v5/reverse"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

_DISTRICT_IN_TEXT = re.compile(r"منطقه\s*(\d{1,2})(?!\d)")
_DISTRICT_NAME = re.compile(r"^(?:منطقه|ناحیه منطقه)\s*(\d{1,2})$|^District\s*(\d{1,2})$", re.IGNORECASE)


def _valid(n: int | None) -> int | None:
    return n if n is not None and 1 <= n <= 22 else None


def district_from_text(text: str | None) -> int | None:
    match = _DISTRICT_IN_TEXT.search(normalize(text))
    return _valid(int(match.group(1))) if match else None


def load_neighbourhood_patterns(path: Path = NEIGHBOURHOODS_FILE) -> list[tuple[re.Pattern, int]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = [(normalize(name), int(d)) for d, names in data.items() if d.isdigit() for name in names]
    entries.sort(key=lambda e: -len(e[0]))  # longest (most specific) first
    patterns = []
    for name, district in entries:
        body = r"\s*".join(re.escape(w) for w in name.split())
        patterns.append((re.compile(rf"(?<!\w){body}(?!\w)"), district))
    return patterns


def district_from_neighbourhood(text: str | None, patterns: list[tuple[re.Pattern, int]]) -> int | None:
    text = normalize(text)
    for pattern, district in patterns:
        if pattern.search(text):
            return district
    return None


# --------------------------------------------------------------------------- polygons

def polygons_from_geojson(geojson: dict) -> dict[int, list[Segment]]:
    """GeoJSON FeatureCollection of district polygons -> {district: edges}.

    The district number is read from a property named ``district``/``region``/``zone``
    or from a name like «منطقه ۶» / "District 6".
    """
    result: dict[int, list[Segment]] = {}
    for feature in geojson.get("features", []):
        props = feature.get("properties") or {}
        district = None
        for key in ("district", "region", "zone", "mantaghe", "municipality_zone"):
            if str(props.get(key, "")).strip():
                try:
                    district = _valid(int(to_latin_digits(str(props[key])).strip()))
                except ValueError:
                    pass
                break
        if district is None:
            for key in ("name", "name:fa", "name_fa", "name:en", "title"):
                district = district_from_name(props.get(key))
                if district:
                    break
        if district is None:
            continue
        geom = feature.get("geometry") or {}
        polys = geom.get("coordinates", [])
        if geom.get("type") == "Polygon":
            polys = [polys]
        elif geom.get("type") != "MultiPolygon":
            continue
        for poly in polys:
            for ring in poly:  # outer ring + holes; even-odd handles holes
                result.setdefault(district, []).extend(ring_to_segments([(lat, lng) for lng, lat, *_ in ring]))
    return result


def district_from_name(name: str | None) -> int | None:
    match = _DISTRICT_NAME.match(normalize(name))
    if not match:
        return None
    return _valid(int(match.group(1) or match.group(2)))


def fetch_osm_district_polygons(http: Http) -> dict[int, list[Segment]]:
    """Download Tehran district boundaries from OpenStreetMap (one Overpass query)."""
    b = TEHRAN
    query = (
        "[out:json][timeout:120];"
        f'relation["boundary"="administrative"]["name"~"منطقه"]({b.south - 0.05},{b.west - 0.05},{b.north + 0.05},{b.east + 0.05});'
        "out geom;"
    )
    data = http.post_form(OVERPASS_URL, {"data": query}).json()
    result: dict[int, list[Segment]] = {}
    for rel in data.get("elements", []):
        tags = rel.get("tags", {})
        district = district_from_name(tags.get("name")) or district_from_name(tags.get("name:en"))
        if district is None or district in result:
            continue
        segments: list[Segment] = []
        for member in rel.get("members", []):
            if member.get("type") != "way" or member.get("role") not in ("outer", "inner", ""):
                continue
            pts = [(p["lat"], p["lon"]) for p in member.get("geometry", [])]
            segments.extend((a[0], a[1], c[0], c[1]) for a, c in zip(pts, pts[1:]))
        if segments:
            result[district] = segments
    log.info("OSM district polygons found for districts: %s", sorted(result))
    return result


def save_polygons(polygons: dict[int, list[Segment]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({str(k): v for k, v in polygons.items()}), encoding="utf-8")


def load_polygons(path: Path) -> dict[int, list[Segment]]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if "features" in raw:
        return polygons_from_geojson(raw)
    return {int(k): [tuple(s) for s in v] for k, v in raw.items()}


# --------------------------------------------------------------------------- resolver

class DistrictResolver:
    def __init__(
        self,
        http: Http | None = None,
        neshan_key: str = "",
        polygons: dict[int, list[Segment]] | None = None,
        cache_file: Path | None = None,
        neighbourhoods_file: Path = NEIGHBOURHOODS_FILE,
    ):
        self.http = http
        self.neshan_key = neshan_key
        self.polygons = polygons or {}
        self.patterns = load_neighbourhood_patterns(neighbourhoods_file)
        self.cache_file = cache_file
        self.cache: dict[str, dict] = {}
        if cache_file and cache_file.exists():
            self.cache = json.loads(cache_file.read_text(encoding="utf-8"))

    def save_cache(self) -> None:
        if self.cache_file:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")

    def neshan_reverse(self, lat: float, lng: float) -> dict:
        key = f"{lat:.5f},{lng:.5f}"
        if key not in self.cache:
            resp = self.http.get(NESHAN_REVERSE_URL, params={"lat": lat, "lng": lng}, headers={"Api-Key": self.neshan_key})
            self.cache[key] = resp.json()
        return self.cache[key]

    def resolve(self, lead: Lead) -> None:
        has_point = lead.lat is not None and lead.lng is not None
        if has_point and self.neshan_key and self.http:
            try:
                info = self.neshan_reverse(lead.lat, lead.lng)
                if not lead.neighbourhood and info.get("neighbourhood"):
                    lead.neighbourhood = info["neighbourhood"]
                if not lead.address and info.get("formatted_address"):
                    lead.address = info["formatted_address"]
                zone = str(info.get("municipality_zone") or "").strip()
                if zone.isdigit() and _valid(int(zone)) and normalize(info.get("city")) in ("", "تهران"):
                    lead.district, lead.district_source = int(zone), "neshan"
                    return
            except Exception as exc:  # network/quota problems shouldn't stop the run
                log.warning("Neshan reverse geocoding failed for %s: %s", lead.name, exc)
        if has_point:
            for district, segments in self.polygons.items():
                if point_in_segments(lead.lat, lead.lng, segments):
                    lead.district, lead.district_source = district, "polygon"
                    return
        district = district_from_text(lead.address)
        if district:
            lead.district, lead.district_source = district, "address"
            return
        district = district_from_neighbourhood(f"{lead.neighbourhood} {lead.address}", self.patterns)
        if district:
            lead.district, lead.district_source = district, "neighbourhood"

    def resolve_all(self, leads: list[Lead]) -> None:
        for lead in leads:
            self.resolve(lead)
        self.save_cache()
