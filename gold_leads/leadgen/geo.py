"""Geometry helpers: Tehran bounding box, search grid, distances, point-in-polygon."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BBox:
    south: float
    west: float
    north: float
    east: float

    def contains(self, lat: float, lng: float) -> bool:
        return self.south <= lat <= self.north and self.west <= lng <= self.east

    def split(self) -> list["BBox"]:
        """Four equal quadrants (used when a map search returns a full page)."""
        mid_lat = (self.south + self.north) / 2
        mid_lng = (self.west + self.east) / 2
        return [
            BBox(self.south, self.west, mid_lat, mid_lng),
            BBox(self.south, mid_lng, mid_lat, self.east),
            BBox(mid_lat, self.west, self.north, mid_lng),
            BBox(mid_lat, mid_lng, self.north, self.east),
        ]

    def tiles(self, rows: int, cols: int) -> list["BBox"]:
        dlat = (self.north - self.south) / rows
        dlng = (self.east - self.west) / cols
        return [
            BBox(self.south + r * dlat, self.west + c * dlng, self.south + (r + 1) * dlat, self.west + (c + 1) * dlng)
            for r in range(rows)
            for c in range(cols)
        ]


# Tehran city (all 22 municipal districts, incl. Shahr-e Rey in the south and Chitgar in the west).
TEHRAN = BBox(south=35.555, west=51.085, north=35.835, east=51.615)


def grid_points(bbox: BBox, step: float) -> list[tuple[float, float]]:
    """Centre points of a regular grid with ``step`` degrees spacing (~1.1 km per 0.01°)."""
    points = []
    lat = bbox.south + step / 2
    while lat < bbox.north:
        lng = bbox.west + step / 2
        while lng < bbox.east:
            points.append((round(lat, 5), round(lng, 5)))
            lng += step
        lat += step
    return points


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


Segment = tuple[float, float, float, float]  # lat1, lng1, lat2, lng2


def point_in_segments(lat: float, lng: float, segments: list[Segment]) -> bool:
    """Even-odd ray casting over polygon edges.

    The edges don't need to be ordered or assembled into rings, and holes work
    automatically — so raw OSM relation member ways can be used directly.
    """
    inside = False
    for lat1, lng1, lat2, lng2 in segments:
        if (lat1 > lat) != (lat2 > lat):
            cross_lng = lng1 + (lat - lat1) * (lng2 - lng1) / (lat2 - lat1)
            if lng < cross_lng:
                inside = not inside
    return inside


def ring_to_segments(ring: list[tuple[float, float]]) -> list[Segment]:
    """[(lat, lng), ...] -> edges (closes the ring if needed)."""
    if len(ring) < 3:
        return []
    if ring[0] != ring[-1]:
        ring = [*ring, ring[0]]
    return [(a[0], a[1], b[0], b[1]) for a, b in zip(ring, ring[1:])]


_HALF_CIRCUMFERENCE = 20037508.342789244


def mercator_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """Web Mercator (EPSG:3857) metres -> (lat, lng) degrees. Some Neshan APIs return metres."""
    lng = x / _HALF_CIRCUMFERENCE * 180.0
    lat = math.degrees(2.0 * math.atan(math.exp(y / _HALF_CIRCUMFERENCE * math.pi)) - math.pi / 2.0)
    return lat, lng
