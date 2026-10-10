"""Merge the same shop found by several sources / several grid searches into one lead."""

from __future__ import annotations

from difflib import SequenceMatcher

from .geo import distance_m
from .models import Lead
from .text import name_key, normalize

SOURCE_PRIORITY = {"google": 0, "osm": 1, "neshan": 2, "mapir": 3}
SAME_PLACE_METERS = 80
_CELL = 0.002  # ~200 m spatial bucket


def similar_names(a: str, b: str) -> bool:
    ka, kb = name_key(a), name_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    shorter, longer = sorted((ka, kb), key=len)
    if len(shorter) >= 3 and shorter in longer.split(" ") + [longer]:
        return True
    return SequenceMatcher(None, ka, kb).ratio() >= 0.85


def same_shop(a: Lead, b: Lead) -> bool:
    if a.google_place_id and a.google_place_id == b.google_place_id:
        return True
    if a.osm_id and a.osm_id == b.osm_id:
        return True
    near = None
    if None not in (a.lat, a.lng, b.lat, b.lng):
        near = distance_m(a.lat, a.lng, b.lat, b.lng) <= SAME_PLACE_METERS
    # Shared phone: a shop and its branch across town may share a number, so require proximity too.
    if set(a.phones) & set(b.phones) and near is not False:
        return True
    if not similar_names(a.name, b.name):
        return False
    if near is None:
        return bool(a.address) and normalize(a.address) == normalize(b.address)
    return near


def merge_into(target: Lead, other: Lead) -> None:
    for attr in ("address", "neighbourhood", "website", "instagram", "category", "business_status",
                 "google_place_id", "google_maps_url", "osm_id", "opening_hours"):
        if not getattr(target, attr) and getattr(other, attr):
            setattr(target, attr, getattr(other, attr))
    if target.lat is None and other.lat is not None:
        target.lat, target.lng = other.lat, other.lng
    if target.rating is None and other.rating is not None:
        target.rating, target.reviews = other.rating, other.reviews
    if len(other.address) > len(target.address) and "google" not in target.sources:
        target.address = other.address
    target.add_phones(other.landlines, other.mobiles)
    for source in other.sources:
        if source not in target.sources:
            target.sources.append(source)


def _cells(lead: Lead) -> list[tuple[int, int]]:
    if lead.lat is None or lead.lng is None:
        return [(-1, -1)]
    r, c = int(lead.lat / _CELL), int(lead.lng / _CELL)
    return [(r + dr, c + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1)]


def dedupe(leads: list[Lead]) -> list[Lead]:
    ordered = sorted(leads, key=lambda l: min((SOURCE_PRIORITY.get(s, 9) for s in l.sources), default=9))
    merged: list[Lead] = []
    buckets: dict[tuple[int, int], list[Lead]] = {}
    by_id: dict[str, Lead] = {}
    by_phone: dict[str, list[Lead]] = {}
    for lead in ordered:
        candidates: list[Lead] = []
        for key in filter(None, (lead.google_place_id and "g" + lead.google_place_id, lead.osm_id and "o" + lead.osm_id)):
            if key in by_id:
                candidates.append(by_id[key])
        for phone in lead.phones:
            candidates.extend(by_phone.get(phone, []))
        for cell in _cells(lead):
            candidates.extend(buckets.get(cell, []))
        match = next((c for c in candidates if same_shop(c, lead)), None)
        if match is None:
            match = lead
            merged.append(lead)
        else:
            merge_into(match, lead)
        own_cell = _cells(match)[len(_cells(match)) // 2]
        if match not in buckets.setdefault(own_cell, []):
            buckets[own_cell].append(match)
        for key in filter(None, (match.google_place_id and "g" + match.google_place_id, match.osm_id and "o" + match.osm_id)):
            by_id[key] = match
        for phone in match.phones:
            if match not in by_phone.setdefault(phone, []):
                by_phone[phone].append(match)
    return merged
