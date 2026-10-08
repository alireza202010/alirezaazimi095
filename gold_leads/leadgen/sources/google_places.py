"""Google Places API (New) Text Search — the richest source: phone, website, rating, reviews.

Docs: https://developers.google.com/maps/documentation/places/web-service/text-search
One query returns at most 60 places (3 pages of 20). To get *every* shop we split
Tehran into tiles and, whenever a tile comes back full, split it into four (quad-tree).
"""

from __future__ import annotations

import logging

from ..geo import TEHRAN, BBox
from ..http import Http
from ..models import Lead
from ..text import extract_phones, is_gold_related, split_phones

log = logging.getLogger(__name__)

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join(
    "places." + f
    for f in (
        "id", "displayName", "formattedAddress", "shortFormattedAddress", "addressComponents", "location",
        "nationalPhoneNumber", "internationalPhoneNumber", "websiteUri", "googleMapsUri", "rating",
        "userRatingCount", "businessStatus", "types", "primaryType", "regularOpeningHours.weekdayDescriptions",
    )
) + ",nextPageToken"
DEFAULT_QUERIES = ("طلا فروشی", "گالری طلا و جواهر")
PAGE_SIZE = 20
MAX_RESULTS = 60  # Google's hard cap per query


def parse_place(place: dict) -> Lead | None:
    name = (place.get("displayName") or {}).get("text", "").strip()
    types = place.get("types") or []
    if not name or not ("jewelry_store" in types or is_gold_related(name)):
        return None
    loc = place.get("location") or {}
    phones = extract_phones(f"{place.get('nationalPhoneNumber', '')} , {place.get('internationalPhoneNumber', '')}")
    landlines, mobiles = split_phones(phones)
    neighbourhood = ""
    for comp in place.get("addressComponents") or []:
        if {"neighborhood", "sublocality_level_2", "sublocality_level_1", "sublocality"} & set(comp.get("types", [])):
            neighbourhood = comp.get("longText", "")
            break
    hours = (place.get("regularOpeningHours") or {}).get("weekdayDescriptions") or []
    return Lead(
        name=name,
        lat=loc.get("latitude"),
        lng=loc.get("longitude"),
        address=place.get("formattedAddress") or place.get("shortFormattedAddress") or "",
        neighbourhood=neighbourhood,
        landlines=landlines,
        mobiles=mobiles,
        website=place.get("websiteUri", ""),
        rating=place.get("rating"),
        reviews=place.get("userRatingCount"),
        category=place.get("primaryType", ""),
        business_status=place.get("businessStatus", ""),
        google_place_id=place.get("id", ""),
        google_maps_url=place.get("googleMapsUri", ""),
        opening_hours=" | ".join(hours),
        sources=["google"],
    )


class GooglePlacesSource:
    name = "google"

    def __init__(self, http: Http, api_key: str, queries=DEFAULT_QUERIES, bbox: BBox = TEHRAN,
                 start_tiles: tuple[int, int] = (4, 6), max_depth: int = 4):
        self.http = http
        self.api_key = api_key
        self.queries = queries
        self.bbox = bbox
        self.start_tiles = start_tiles
        self.max_depth = max_depth

    def search_tile(self, query: str, tile: BBox) -> list[dict]:
        places: list[dict] = []
        body = {
            "textQuery": query,
            "languageCode": "fa",
            "regionCode": "IR",
            "pageSize": PAGE_SIZE,
            "locationRestriction": {
                "rectangle": {
                    "low": {"latitude": tile.south, "longitude": tile.west},
                    "high": {"latitude": tile.north, "longitude": tile.east},
                }
            },
        }
        headers = {"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": FIELD_MASK}
        while True:
            data = self.http.post_json(SEARCH_URL, body, headers=headers).json()
            places.extend(data.get("places", []))
            token = data.get("nextPageToken")
            if not token or len(places) >= MAX_RESULTS:
                return places
            body = {**body, "pageToken": token}

    def collect(self) -> list[Lead]:
        leads: list[Lead] = []
        for query in self.queries:
            stack = [(tile, 0) for tile in self.bbox.tiles(*self.start_tiles)]
            while stack:
                tile, depth = stack.pop()
                try:
                    places = self.search_tile(query, tile)
                except Exception as exc:
                    log.warning("Google search failed for %s in %s: %s", query, tile, exc)
                    continue
                if len(places) >= MAX_RESULTS and depth < self.max_depth:
                    stack.extend((sub, depth + 1) for sub in tile.split())  # tile is saturated
                    continue
                leads.extend(lead for lead in map(parse_place, places) if lead)
            log.info("Google: %r -> %d raw results so far", query, len(leads))
        return leads
