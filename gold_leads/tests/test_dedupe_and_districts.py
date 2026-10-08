import json

from conftest import FakeHttp

from leadgen.dedupe import dedupe
from leadgen.districts import (
    DistrictResolver,
    district_from_name,
    district_from_text,
    load_polygons,
    polygons_from_geojson,
)
from leadgen.models import Lead


def test_same_shop_from_two_sources_is_merged():
    google = Lead(name="گالری طلای کیان", lat=35.67450, lng=51.42100, google_place_id="g1",
                  landlines=["02155667788"], rating=4.5, reviews=80, sources=["google"])
    neshan = Lead(name="طلا و جواهر کیان", lat=35.67460, lng=51.42110, neighbourhood="بازار", sources=["neshan"])
    neshan_dup = Lead(name="طلا و جواهر کیان", lat=35.67460, lng=51.42110, sources=["neshan"])
    merged = dedupe([neshan, google, neshan_dup])
    assert len(merged) == 1
    lead = merged[0]
    assert lead.google_place_id == "g1" and lead.neighbourhood == "بازار"
    assert lead.sources == ["google", "neshan"]


def test_neighbouring_bazaar_shops_stay_separate():
    a = Lead(name="طلای کیان", lat=35.6745, lng=51.4210, sources=["neshan"])
    b = Lead(name="جواهری مهرگان", lat=35.6746, lng=51.4211, sources=["neshan"])
    assert len(dedupe([a, b])) == 2


def test_branches_of_a_chain_far_apart_stay_separate():
    a = Lead(name="گالری طلای کیان", lat=35.6745, lng=51.4210, landlines=["02155667788"], sources=["google"])
    b = Lead(name="گالری طلای کیان", lat=35.7745, lng=51.4210, landlines=["02155667788"], sources=["google"])
    assert len(dedupe([a, b])) == 2


def test_district_from_text_and_name():
    assert district_from_text("تهران، منطقه ۱۲، بازار") == 12
    assert district_from_text("منطقه 25") is None
    assert district_from_name("منطقه ۶") == 6
    assert district_from_name("District 22") == 22
    assert district_from_name("منطقه ۶ ناحیه ۲") is None


SQUARE = [[51.40, 35.70], [51.45, 35.70], [51.45, 35.75], [51.40, 35.75], [51.40, 35.70]]
HOLE = [[51.42, 35.72], [51.43, 35.72], [51.43, 35.73], [51.42, 35.73], [51.42, 35.72]]


def test_polygon_resolution_with_holes(tmp_path):
    geojson = {"type": "FeatureCollection", "features": [
        {"properties": {"name": "منطقه ۶"}, "geometry": {"type": "Polygon", "coordinates": [SQUARE, HOLE]}},
    ]}
    path = tmp_path / "d.geojson"
    path.write_text(json.dumps(geojson), encoding="utf-8")
    polygons = load_polygons(path)
    assert polygons.keys() == polygons_from_geojson(geojson).keys() == {6}
    resolver = DistrictResolver(polygons=polygons)
    inside, in_hole, outside = (Lead(name="x", lat=35.71, lng=51.41), Lead(name="y", lat=35.725, lng=51.425),
                                Lead(name="z", lat=35.80, lng=51.41))
    resolver.resolve_all([inside, in_hole, outside])
    assert (inside.district, inside.district_source) == (6, "polygon")
    assert in_hole.district is None and outside.district is None


def test_neshan_reverse_is_used_and_cached(tmp_path):
    http = FakeHttp(lambda m, u, k: {"municipality_zone": "3", "neighbourhood": "ونک", "city": "تهران"})
    resolver = DistrictResolver(http=http, neshan_key="k", cache_file=tmp_path / "rev.json")
    a, b = Lead(name="a", lat=35.757, lng=51.41), Lead(name="b", lat=35.757, lng=51.41)
    resolver.resolve_all([a, b])
    assert (a.district, a.district_source, a.neighbourhood) == (3, "neshan", "ونک")
    assert b.district == 3 and len(http.calls) == 1  # second lookup served from cache
    assert (tmp_path / "rev.json").exists()


def test_fallback_to_address_then_neighbourhood():
    resolver = DistrictResolver()
    by_address = Lead(name="a", address="تهران، منطقه ۲۲، بلوار کاج")
    by_name = Lead(name="b", address="خیابان شریعتی، قلهک، پلاک ۱")
    by_spacing = Lead(name="c", address="بلوار دریا، سعادت‌آباد")
    unknown = Lead(name="d", address="خیابان اصلی")
    resolver.resolve_all([by_address, by_name, by_spacing, unknown])
    assert (by_address.district, by_address.district_source) == (22, "address")
    assert (by_name.district, by_name.district_source) == (3, "neighbourhood")
    assert by_spacing.district == 2
    assert unknown.district is None and unknown.district_label == "نامشخص"
