"""The Lead record shared by every stage of the pipeline."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .text import name_key, to_persian_digits

UNKNOWN_DISTRICT = "نامشخص"


def district_label(district: int | None) -> str:
    return f"منطقه {to_persian_digits(district)}" if district else UNKNOWN_DISTRICT


@dataclass
class Lead:
    name: str
    lat: float | None = None
    lng: float | None = None
    address: str = ""
    neighbourhood: str = ""
    district: int | None = None
    district_source: str = ""  # neshan | polygon | address | neighbourhood
    landlines: list[str] = field(default_factory=list)
    mobiles: list[str] = field(default_factory=list)
    website: str = ""
    instagram: str = ""
    rating: float | None = None
    reviews: int | None = None
    category: str = ""
    business_status: str = ""  # OPERATIONAL / CLOSED_TEMPORARILY / CLOSED_PERMANENTLY
    google_place_id: str = ""
    google_maps_url: str = ""
    osm_id: str = ""
    opening_hours: str = ""
    sources: list[str] = field(default_factory=list)
    # Filled by the Claude enrichment step.
    shop_type: str = ""
    size: str = ""
    branches: int = 0
    instagram_followers: int = 0
    sells_bullion: str = ""  # yes / no / "" (unknown) — sells شمش / آبشده / سکه
    bullion_brands: list[str] = field(default_factory=list)
    wholesale: str = ""  # yes / no / ""
    agency_fit: str = ""  # high / medium / low / ""
    fit_reason: str = ""
    ai_note: str = ""
    outreach_message: str = ""
    enriched: bool = False
    # Filled by scoring.
    score: int = 0
    tier: str = ""

    @property
    def lead_id(self) -> str:
        """Stable id: Google place id > OSM id > hash of name + rounded location."""
        if self.google_place_id:
            return f"g:{self.google_place_id}"
        if self.osm_id:
            return f"o:{self.osm_id}"
        loc = f"{self.lat:.4f},{self.lng:.4f}" if self.lat is not None and self.lng is not None else ""
        digest = hashlib.sha1(f"{name_key(self.name)}|{loc}".encode()).hexdigest()[:12]
        return f"h:{digest}"

    @property
    def district_label(self) -> str:
        return district_label(self.district)

    @property
    def phones(self) -> list[str]:
        return self.landlines + self.mobiles

    @property
    def neshan_url(self) -> str:
        if self.lat is None or self.lng is None:
            return ""
        return f"https://neshan.org/maps/@{self.lat:.6f},{self.lng:.6f},18z"

    @property
    def maps_url(self) -> str:
        if self.google_maps_url:
            return self.google_maps_url
        if self.lat is None or self.lng is None:
            return ""
        return f"https://www.google.com/maps/search/?api=1&query={self.lat:.6f},{self.lng:.6f}"

    def add_phones(self, landlines: list[str] = (), mobiles: list[str] = ()) -> None:
        for phone in landlines:
            if phone not in self.landlines:
                self.landlines.append(phone)
        for phone in mobiles:
            if phone not in self.mobiles:
                self.mobiles.append(phone)
