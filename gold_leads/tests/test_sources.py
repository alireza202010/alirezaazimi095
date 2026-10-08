from conftest import FakeHttp

from leadgen.geo import BBox
from leadgen.sources.google_places import MAX_RESULTS, GooglePlacesSource, parse_place
from leadgen.sources.neshan import NeshanSource, parse_items
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


def test_neshan_grid_sweep_sends_key():
    http = FakeHttp(lambda m, u, k: {"items": []})
    NeshanSource(http, "secret", terms=("طلا",), step=0.05, bbox=BBox(35.6, 51.3, 35.7, 51.4)).collect()
    assert http.calls and all(c[2]["headers"]["Api-Key"] == "secret" for c in http.calls)
    assert len(http.calls) == 4  # 2x2 grid


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
