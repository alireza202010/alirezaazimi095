import json

import pytest
from conftest import FakeHttp, FakeHTTPError

from leadgen.geo import BBox
from leadgen.sources.google_places import MAX_RESULTS, GooglePlacesSource, parse_place
from leadgen.sources.mapir import MapirSource
from leadgen.sources.mapir import parse_items as parse_mapir
from leadgen.sources.neshan import NeshanAccessError, NeshanSource, item_point, parse_items
from leadgen.sources.osm import parse_elements

GOOGLE_PLACE = {
    "id": "ChIJ123",
    "displayName": {"text": "گالری طلای کیان"},
    "formattedAddress": "تهران، بازار بزرگ، پاساژ طلا، پلاک ۱۲",
    "location": {"latitude": 35.6745, "longitude": 51.4210},
    "nationalPhoneNumber": "021 5566 7788",
    "internationalPhoneNumber": "+98 21 5566 7788",
    "websiteUri": "https://kiangold.ir",
    "googleMapsUri": "https://maps.google.com/?cid=1",
    "rating": 4.7,
    "userRatingCount": 120,
    "businessStatus": "OPERATIONAL",
    "types": ["jewelry_store", "store"],
    "addressComponents": [{"longText": "بازار", "types": ["sublocality_level_1", "political"]}],
}


def test_parse_google_place():
    lead = parse_place(GOOGLE_PLACE)
    assert lead.name == "گالری طلای کیان"
    assert lead.landlines == ["02155667788"] and lead.mobiles == []
    assert lead.reviews == 120 and lead.rating == 4.7
    assert lead.neighbourhood == "بازار"
    assert lead.lead_id == "g:ChIJ123"


def test_parse_google_skips_non_gold():
    assert parse_place({**GOOGLE_PLACE, "displayName": {"text": "کافه"}, "types": ["cafe"]}) is None


def test_google_splits_saturated_tiles():
    calls = []

    def handler(method, url, kwargs):
        rect = kwargs["json"]["locationRestriction"]["rectangle"]
        size = rect["high"]["latitude"] - rect["low"]["latitude"]
        calls.append(size)
        if size > 0.06 and "pageToken" not in kwargs["json"]:  # big tile: first page says "more"
            return {"places": [GOOGLE_PLACE] * 20, "nextPageToken": "t"}
        if size > 0.06:
            return {"places": [GOOGLE_PLACE] * 20, "nextPageToken": "t2"}
        return {"places": [{**GOOGLE_PLACE, "id": f"p{len(calls)}"}]}

    source = GooglePlacesSource(FakeHttp(handler), "key", queries=("طلا",), bbox=BBox(35.6, 51.3, 35.7, 51.4),
                                start_tiles=(1, 1), max_depth=2)
    leads = source.collect()
    assert MAX_RESULTS == 60
    assert calls[:3] == [calls[0]] * 3  # three pages of the saturated tile
    assert len(leads) == 4  # split into 4 sub-tiles, one shop each


def test_parse_neshan_items():
    items = [
        {"title": "طلا فروشی رضایی", "address": "خیابان ولیعصر", "neighbourhood": "یوسف آباد",
         "region": "تهران، منطقه ۶", "type": "shop", "category": "place", "location": {"x": 51.41, "y": 35.73}},
        {"title": "نانوایی", "location": {"x": 51.41, "y": 35.73}},
        {"title": "طلای شیراز", "location": {"x": 52.5, "y": 29.6}},  # outside Tehran
    ]
    leads = parse_items(items)
    assert len(leads) == 1
    assert leads[0].lat == 35.73 and leads[0].lng == 51.41
    assert "منطقه ۶" in leads[0].address


def test_neshan_grid_sweep_uses_v3_with_cell_bounds():
    http = FakeHttp(lambda m, u, k: {"items": []})
    source = NeshanSource(http, "secret", terms=("طلا",), step=0.05, bbox=BBox(35.6, 51.3, 35.7, 51.4))
    source.collect()
    assert source.version == "v3"
    assert all(c[2]["headers"]["Api-Key"] == "secret" for c in http.calls)
    assert len(http.calls) == 1 + 4  # endpoint probe + 2x2 grid
    q = json.loads(http.calls[-1][2]["params"]["q"])
    assert q["term"] == "طلا" and q["bound"]["northEast"]["latitude"] > q["center"]["latitude"]


def test_neshan_falls_back_to_v1_when_v3_is_not_allowed():
    def handler(method, url, kwargs):
        if "/v3/" in url:
            raise FakeHTTPError(403)
        return {"items": []}

    source = NeshanSource(FakeHttp(handler), "k")
    assert source.detect_version() == "v1"


def test_neshan_key_without_search_access_fails_fast():
    def handler(method, url, kwargs):
        raise FakeHTTPError(403)

    http = FakeHttp(handler)
    with pytest.raises(NeshanAccessError, match="Search API"):
        NeshanSource(http, "k").collect()
    assert len(http.calls) == 2  # one probe per endpoint, not thousands of failing grid calls


def test_neshan_item_point_handles_degrees_and_mercator():
    assert item_point({"location": {"x": 51.42, "y": 35.67}}) == (35.67, 51.42)
    lat, lng = item_point({"location": {"x": 5724040.0, "y": 4254500.0}})  # metres
    assert 35.5 < lat < 35.9 and 51.2 < lng < 51.6
    assert item_point({"location": {"latitude": 35.7, "longitude": 51.4}}) == (35.7, 51.4)
    assert item_point({}) is None


def test_parse_mapir_items():
    items = [
        {"title": "طلای آبشده نیکان", "address": "خیابان ۱۵ خرداد", "city": "تهران", "region": "منطقه ۱۲",
         "neighborhood": "بازار", "fclass": "poi", "geom": {"type": "Point", "coordinates": [51.421, 35.6745]}},
        {"title": "طلای کرج", "city": "کرج", "geom": {"type": "Point", "coordinates": [51.42, 35.67]}},
        {"title": "نانوایی", "city": "تهران", "geom": {"type": "Point", "coordinates": [51.42, 35.67]}},
    ]
    leads = parse_mapir(items)
    assert len(leads) == 1 and leads[0].sources == ["mapir"]
    assert (leads[0].lat, leads[0].lng) == (35.6745, 51.421) and "منطقه ۱۲" in leads[0].address


def test_mapir_sends_key_header():
    http = FakeHttp(lambda m, u, k: {"value": []})
    MapirSource(http, "mk").search("طلا", 35.7, 51.4)
    method, url, kwargs = http.calls[0]
    assert (method, url) == ("POST", "https://map.ir/search/v2")
    assert kwargs["headers"]["x-api-key"] == "mk" and kwargs["json"]["$select"] == "poi"


def test_parse_osm_elements():
    elements = [
        {"type": "node", "id": 1, "lat": 35.70, "lon": 51.40,
         "tags": {"shop": "jewelry", "name": "Kian", "name:fa": "جواهری کیان",
                  "phone": "+98 21 3311 2233;+98 912 123 4567", "contact:instagram": "kian.gold"}},
        {"type": "way", "id": 2, "center": {"lat": 35.71, "lon": 51.41}, "tags": {"shop": "bakery", "name": "نان"}},
    ]
    leads = parse_elements(elements)
    assert len(leads) == 1
    lead = leads[0]
    assert lead.name == "جواهری کیان" and lead.osm_id == "node/1"
    assert lead.landlines == ["02133112233"] and lead.mobiles == ["09121234567"]
    assert lead.instagram == "https://instagram.com/kian.gold"
