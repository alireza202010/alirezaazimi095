"""OpenStreetMap via Overpass — free, no key. Coverage is partial but often has phones."""

from __future__ import annotations

import logging

from ..geo import TEHRAN, BBox
from ..http import Http
from ..models import Lead
from ..text import extract_phones, is_gold_related, normalize_instagram, split_phones

log = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def build_query(bbox: BBox = TEHRAN) -> str:
    b = f"({bbox.south},{bbox.west},{bbox.north},{bbox.east})"
    return (
        "[out:json][timeout:180];("
        f'nwr["shop"~"^(jewelry|jewellery|gold|gold_buyer)$"]{b};'
        f'nwr["craft"~"^(goldsmith|jeweller)$"]{b};'
        f'nwr["shop"]["name"~"طلا|جواهر|زرگر"]{b};'
        ");out center tags;"
    )


def parse_elements(elements: list[dict]) -> list[Lead]:
    leads = []
    for el in elements:
        tags = el.get("tags") or {}
        name = tags.get("name:fa") or tags.get("name") or ""
        shop = tags.get("shop", "")
        if not name or not (shop in ("jewelry", "jewellery", "gold", "gold_buyer") or tags.get("craft") or is_gold_related(name)):
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lng = el.get("lon") or (el.get("center") or {}).get("lon")
        phone_text = " , ".join(
            tags.get(k, "") for k in ("phone", "contact:phone", "mobile", "contact:mobile", "phone:mobile")
        )
        landlines, mobiles = split_phones(extract_phones(phone_text))
        address = tags.get("addr:full") or " ".join(
            filter(None, [tags.get("addr:street"), tags.get("addr:place"), tags.get("addr:housenumber")])
        )
        leads.append(
            Lead(
                name=name,
                lat=float(lat) if lat is not None else None,
                lng=float(lng) if lng is not None else None,
                address=address,
                neighbourhood=tags.get("addr:suburb") or tags.get("addr:neighbourhood") or "",
                landlines=landlines,
                mobiles=mobiles,
                website=tags.get("website") or tags.get("contact:website") or "",
                instagram=normalize_instagram(tags.get("contact:instagram") or tags.get("instagram")),
                opening_hours=tags.get("opening_hours", ""),
                category=shop or tags.get("craft", ""),
                osm_id=f"{el.get('type')}/{el.get('id')}",
                sources=["osm"],
            )
        )
    return leads


class OsmSource:
    name = "osm"

    def __init__(self, http: Http, bbox: BBox = TEHRAN, url: str = OVERPASS_URL):
        self.http = http
        self.bbox = bbox
        self.url = url

    def collect(self) -> list[Lead]:
        resp = self.http.post_form(self.url, {"data": build_query(self.bbox)})
        leads = parse_elements(resp.json().get("elements", []))
        log.info("OSM: %d gold shops", len(leads))
        return leads
