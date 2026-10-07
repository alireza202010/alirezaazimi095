from pathlib import Path

import pytest
from pydantic import ValidationError

from trip.guide import PACE_HOURS, build_days, detect_city, exclusion_reason, guide, load_cities, score
from trip.guide_models import CATEGORIES, GuideRequest

CITIES = load_cities(Path(__file__).resolve().parent.parent / "data" / "cities.json")
BY_ID = {c.id: c for c in CITIES}


def req(**kw) -> GuideRequest:
    base = dict(city="mashhad", days=3, group="couple", interests=["history"], budget="moderate", season="spring")
    base.update(kw)
    return GuideRequest(**base)


def place(city, name):
    return next(p for p in BY_ID[city].places if p.name == name)


def test_dataset():
    assert len(CITIES) >= 8 and sum(len(c.places) for c in CITIES) >= 100
    for c in CITIES:
        assert len(c.places) >= 10 and c.foods and len(c.categories) >= 5
    assert {c for city in CITIES for c in city.categories} == set(CATEGORIES)


@pytest.mark.parametrize("text,expected", [
    ("سلام، میخوام برم مشهد", "mashhad"), ("مقصدم مشهد مقدس است", "mashhad"),
    ("كرمانشاه", "kermanshah"), ("Isfahan", "isfahan"), ("جزیره کیش", "kish"), ("لندن", None),
])
def test_detect_city(text, expected):
    found = detect_city(text, CITIES)
    assert (found.id if found else None) == expected


def test_exclusions():
    rafting = place("kermanshah", "رفتینگ در رودخانه سیروان")
    assert exclusion_reason(rafting, req(season="winter")) == "در زمستان مناسب نیست"
    assert exclusion_reason(rafting, req(season="summer", budget="moderate")) == "بیشتر از بودجه انتخابی"
    assert exclusion_reason(rafting, req(season="summer", budget="premium")) is None
    assert exclusion_reason(rafting, req(season="summer", budget="premium", days=1)) == "سفر یک‌روزه کافی نیست"


def test_score_prefers_interest_and_respects_group():
    city = BY_ID["mashhad"]
    park = place("mashhad", "پارک آبی موج‌های آبی")
    haram = place("mashhad", "حرم امام رضا (ع)")
    r = req(interests=["thrill"])
    assert score(park, r, city) > score(haram, r, city)
    hike = place("mashhad", "آبشار اخلمد")
    assert score(hike, req(interests=["nature"], group="family_kids"), city) < \
        score(hike, req(interests=["nature"], group="couple"), city)


def test_user_examples():
    mashhad = guide(req(interests=["thrill"], season="summer", group="friends"), BY_ID["mashhad"])
    top = mashhad.sections[0]
    assert top.interest == "thrill" and top.places[0].name == "پارک آبی موج‌های آبی"
    assert "مشهد" in top.places[0].pitch and "هیجان" in top.places[0].pitch

    kermanshah = guide(req(city="kermanshah", interests=["history"], season="autumn"), BY_ID["kermanshah"])
    assert kermanshah.sections[0].places[0].name == "طاق بستان"
    assert "رفتینگ در رودخانه سیروان" in kermanshah.excluded["در پاییز مناسب نیست"]


def test_itinerary_rules():
    r = req(city="shiraz", days=3, interests=["history"], pace="balanced")
    g = guide(r, BY_ID["shiraz"])
    assert len(g.itinerary) == 3
    assert all(p.trip == "city" for p in g.itinerary[0].places)  # arrival day stays in town
    names = [p.name for d in g.itinerary for p in d.places]
    assert len(names) == len(set(names))
    for day in g.itinerary:
        trips = [p for p in day.places if p.trip != "city"]
        assert len(trips) <= 1
        assert day.hours <= max(PACE_HOURS[r.pace], 9.0)


def test_build_days_capacity_and_left_out():
    city = BY_ID["isfahan"]
    ranked = [(p, 1.0) for p in city.places if p.trip == "city"]
    days, left = build_days(ranked, req(city="isfahan", days=1, pace="relaxed"))
    assert sum(p.hours for p in days[0]) <= PACE_HOURS["relaxed"]
    assert left and len(days[0]) + len(left) == len(ranked)


def test_invalid_request():
    with pytest.raises(ValidationError):
        req(group="aliens")
    with pytest.raises(ValidationError):
        req(season="monsoon")
    with pytest.raises(ValidationError):
        req(days=0)


def test_api(client):
    cities = client.get("/api/cities").json()
    assert any(c["id"] == "kermanshah" and "history" in c["categories"] for c in cities)
    assert client.get("/api/cities/detect", params={"q": "میرم تبریز"}).json() == {"city": "tabriz"}
    assert set(client.get("/api/guide/meta").json()) >= {"groups", "budgets", "seasons", "categories", "paces"}
    res = client.post("/api/guide", json={"city": "kish", "days": 2, "interests": ["thrill"], "season": "summer",
                                          "budget": "premium", "group": "friends"})
    data = res.json()
    assert res.status_code == 200 and data["sections"][0]["places"]
    assert any("گرم" in t for t in data["tips"])
    assert client.post("/api/guide", json={"city": "atlantis", "days": 2}).status_code == 404
