from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from trip.catalog import INTERESTS
from trip.costs import estimate, overlaps_nowruz, rooms_needed, season_score
from trip.data import load_destinations
from trip.itinerary import build_itinerary
from trip.jalali import gregorian_to_jalali, is_nowruz
from trip.models import TripRequest
from trip.recommender import duration_fit, exclusion_reason, interest_score

DATA = Path(__file__).resolve().parent.parent / "data" / "destinations.json"
DESTS = {d.id: d for d in load_destinations(DATA)}


def req(**kw) -> TripRequest:
    base = dict(budget=100_000_000, start_date=date(2026, 11, 5), end_date=date(2026, 11, 10),
                adults=2, usd_rate=100_000)
    base.update(kw)
    return TripRequest(**base)


def test_dataset_is_valid_and_covers_every_interest():
    assert len(DESTS) >= 35
    assert {d.scope.value for d in DESTS.values()} == {"domestic", "international"}
    for interest in INTERESTS:
        assert any(d.tags.get(interest, 0) >= 0.8 for d in DESTS.values()), interest


def test_jalali_and_nowruz():
    assert gregorian_to_jalali(2027, 3, 21) == (1406, 1, 1)
    assert is_nowruz(date(2027, 3, 21)) and is_nowruz(date(2027, 4, 2)) and not is_nowruz(date(2027, 4, 3))
    assert overlaps_nowruz(req(start_date=date(2027, 3, 15), end_date=date(2027, 3, 22)))
    assert not overlaps_nowruz(req())


def test_request_validation():
    with pytest.raises(ValidationError):
        req(end_date=date(2026, 11, 5))
    with pytest.raises(ValidationError):
        req(end_date=date(2027, 1, 5))  # > 30 nights
    with pytest.raises(ValidationError):
        req(interests=["unknown"])
    assert req().nights == 5 and req().days == 6


def test_rooms():
    assert rooms_needed(1, 0) == 1
    assert rooms_needed(2, 2) == 1
    assert rooms_needed(2, 3) == 2
    assert rooms_needed(5, 0) == 3


def test_cost_breakdown_adds_up_and_scales():
    d = DESTS["istanbul"]
    r = req()
    c = estimate(d, r, "standard", nowruz=False)
    parts = c.transport + c.lodging + c.daily + c.visa + c.contingency
    assert abs(parts - c.total) <= 50_000  # rounding to 10k toman per line
    # transport 250*2 + lodging 100*1*5 + daily 60*6*2 = 1720 USD, +10% => 1892 USD
    assert c.total == 189_200_000
    assert estimate(d, r, "luxury", False).total > c.total > estimate(d, r, "economy", False).total
    assert estimate(d, r, "standard", nowruz=True).total > c.total
    assert estimate(d, req(usd_rate=200_000), "standard", False).total == 2 * c.total


def test_season_and_filters():
    assert season_score(DESTS["dubai"], req(start_date=date(2027, 7, 1), end_date=date(2027, 7, 5))) == 1
    assert exclusion_reason(DESTS["dubai"], req(start_date=date(2027, 7, 1), end_date=date(2027, 7, 5))) \
        == "آب‌وهوای نامناسب در تاریخ سفر"
    assert exclusion_reason(DESTS["paris"], req(visa_free_only=True)) == "نیاز به ویزای قبلی"
    assert exclusion_reason(DESTS["istanbul"], req(visa_free_only=True)) is None
    assert exclusion_reason(DESTS["bali"], req(max_travel_hours=5)) == "مسیر طولانی‌تر از حد انتخابی"
    assert exclusion_reason(DESTS["bali"], req(end_date=date(2026, 11, 8))) == "مدت سفر برای این مقصد کوتاه است"
    assert exclusion_reason(DESTS["kish"], req(scope="international")) is not None
    assert exclusion_reason(DESTS["dizin"], req(interests=["pilgrimage"])) == "هم‌خوانی کم با علایق شما"


def test_scoring_helpers():
    assert interest_score(DESTS["mashhad"], ["pilgrimage"]) == 1
    assert interest_score(DESTS["mashhad"], []) == 0.6
    assert duration_fit(DESTS["kashan"], 3) == 1 and duration_fit(DESTS["kashan"], 6) < 1


def test_itinerary_shape():
    plan = build_itinerary(DESTS["istanbul"], req(interests=["shopping"]))
    assert len(plan) == 6
    assert plan[0].title == "ورود و استقرار" and plan[-1].title == "بازگشت"
    assert "حرکت به سمت مبدأ" in plan[-1].activities
    assert any("بازار" in a or "مراکز خرید" in a for a in plan[-1].activities)
    names = [a for p in plan for a in p.activities]
    assert len(names) == len(set(names))
    assert plan[0].date_label == "پنجشنبه ۱۴ آبان"
    short = build_itinerary(DESTS["kashan"], req(end_date=date(2026, 11, 6)))
    assert [p.title for p in short] == ["ورود و استقرار", "بازگشت"]
