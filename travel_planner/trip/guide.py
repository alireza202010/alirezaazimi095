"""City guide: recommends places inside one city from the traveler's answers."""

import json
import re
from pathlib import Path

from trip.guide_models import (
    BUDGETS, CATEGORIES, GROUPS, MAX_PRICE, PACES, PRICE_RANK, PRICES, SEASONS, TIME_ORDER, TIMES,
    City, GuideDay, GuideRequest, GuideResponse, InterestSection, Place, PlaceSuggestion,
)

# Activity hours available per day by pace.
PACE_HOURS = {"relaxed": 5.0, "balanced": 7.0, "packed": 9.0}
TRIP_HOURS = {"half_day": 5.0, "full_day": 9.0}
PER_SECTION = 3
MUST_SEE = 4

PITCHES = [
    "اگر در {city} دنبال {phrase} هستی، {name} گزینه خیلی خوبی است.",
    "برای {phrase} در {city}، {name} را از دست نده.",
    "{name} یکی از بهترین انتخاب‌ها برای {phrase} در {city} است.",
]
PHRASES = {
    "thrill": "هیجان و ماجراجویی",
    "history": "جاهای تاریخی و فرهنگی",
    "pilgrimage": "زیارت و فضای معنوی",
    "nature": "طبیعت و هوای تازه",
    "fun": "تفریح و سرگرمی",
    "shopping": "خرید و بازارگردی",
    "food": "غذای خوب و رستوران‌گردی",
    "relaxation": "آرامش و حال خوب",
    "museum": "موزه‌گردی",
    "night": "یک شب‌گردی دلچسب",
}


def load_cities(path: Path) -> list[City]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    cities = [City(**c) for c in raw["cities"]]
    ids = [p.id for c in cities for p in c.places] + [c.id for c in cities]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate city or place ids")
    return cities


def _normalize(text: str) -> str:
    text = text.replace("ي", "ی").replace("ك", "ک").replace("‌", " ").lower()
    return re.sub(r"\s+", " ", text).strip()


def detect_city(text: str, cities: list[City]) -> City | None:
    """Find a city mentioned in free text such as «میخوام برم مشهد»."""
    norm = _normalize(text)
    best: tuple[int, City] | None = None
    for city in cities:
        for alias in city.aliases + [city.name]:
            a = _normalize(alias)
            if a and a in norm and (best is None or len(a) > best[0]):
                best = (len(a), city)
    return best[1] if best else None


def exclusion_reason(place: Place, req: GuideRequest) -> str | None:
    if req.season not in place.seasons:
        return f"در {SEASONS[req.season]} مناسب نیست"
    if PRICE_RANK[place.price] > MAX_PRICE[req.budget]:
        return "بیشتر از بودجه انتخابی"
    if place.trip == "full_day" and req.days < 2:
        return "سفر یک‌روزه کافی نیست"
    return None


def score(place: Place, req: GuideRequest, city: City) -> float:
    if req.interests:
        matches = [i for i in req.interests if i in place.categories]
        # Main interest counts most; extra matches add a bonus.
        interest = 0.0 if not matches else min(1.0, 0.7 + 0.15 * (len(matches) - 1)
                                               + (0.15 if req.interests[0] in matches else 0))
    else:
        interest = 0.6
    popularity = place.popularity / 3

    group = 1.0
    if req.group == "family_kids" and not place.kids:
        group = 0.3
    elif req.group == "family_elderly" and not place.elderly:
        group = 0.3
    elif req.group == "friends" and ({"thrill", "night"} & set(place.categories)):
        group = 1.15
    elif req.group == "couple" and ({"relaxation", "night"} & set(place.categories)):
        group = 1.1
    elif req.group == "family_kids" and "fun" in place.categories:
        group = 1.15

    weather = 1.0
    if req.season in city.hot_seasons or req.season in city.cold_seasons:
        weather = 1.1 if place.indoor else 0.9

    return round(100 * (0.6 * interest + 0.25 * popularity + 0.15) * group * weather, 1)


def _suggest(place: Place, req: GuideRequest, city: City, sc: float, focus: str | None, i: int) -> PlaceSuggestion:
    focus = focus or next((c for c in req.interests if c in place.categories), place.categories[0])
    pitch = PITCHES[i % len(PITCHES)].format(city=city.name, phrase=PHRASES[focus], name=place.name)
    tips = [place.tip] if place.tip else []
    if not place.indoor and req.season in city.hot_seasons and place.best_time not in {"evening", "night"}:
        tips.append("هوا گرم است؛ صبح زود یا نزدیک غروب بروید.")
    if not place.indoor and req.season in city.cold_seasons:
        tips.append("هوا سرد است؛ لباس گرم کافی همراه داشته باشید.")
    if place.trip == "half_day":
        tips.append("بیرون از شهر است؛ نصف روز برایش کنار بگذارید.")
    elif place.trip == "full_day":
        tips.append("سفری یک‌روزه بیرون از شهر است.")
    return PlaceSuggestion(
        id=place.id, name=place.name, pitch=pitch, description=place.description,
        categories=place.categories, category_labels=[CATEGORIES[c] for c in place.categories],
        price=place.price, price_label=PRICES[place.price], hours=place.hours,
        best_time_label=TIMES[place.best_time], area=place.area, trip=place.trip,
        kids=place.kids, indoor=place.indoor, score=sc, tips=tips,
    )


def _place_hours(place: Place) -> float:
    return TRIP_HOURS.get(place.trip, place.hours)


def build_days(ranked: list[tuple[Place, float]], req: GuideRequest) -> tuple[list[list[Place]], list[Place]]:
    """Assign places to days: out-of-town trips get their own day, city places are grouped by area."""
    capacity = PACE_HOURS[req.pace]
    days: list[list[Place]] = [[] for _ in range(req.days)]
    used = [0.0] * req.days
    left_out: list[Place] = []

    # At most one out-of-town trip per day, and always keep at least one day in the city.
    trips = [p for p, _ in ranked if p.trip != "city"]
    city_places = [p for p, _ in ranked if p.trip == "city"]
    trip_days = list(range(1, req.days)) if req.days > 1 else [0]  # keep the arrival day in the city
    for place in trips:
        if not trip_days:
            left_out.append(place)
            continue
        d = trip_days.pop(0)
        days[d].append(place)
        used[d] = TRIP_HOURS[place.trip]

    # Seed each day with the best remaining place, then fill it with places from the same area first.
    pool = list(city_places)
    for d in range(req.days):
        while pool:
            same_area = {p.area for p in days[d]}
            fits = [p for p in pool if used[d] + p.hours <= capacity]
            if not fits:
                break
            pick = next((p for p in fits if p.area in same_area), fits[0])
            days[d].append(pick)
            used[d] += pick.hours
            pool.remove(pick)
    left_out.extend(pool)
    for day in days:
        day.sort(key=lambda p: (p.trip == "city", TIME_ORDER[p.best_time]))
    return days, left_out


def guide(req: GuideRequest, city: City) -> GuideResponse:
    excluded: dict[str, list[str]] = {}
    ranked: list[tuple[Place, float]] = []
    for place in city.places:
        reason = exclusion_reason(place, req)
        if reason:
            excluded.setdefault(reason, []).append(place.name)
        else:
            ranked.append((place, score(place, req, city)))
    ranked.sort(key=lambda x: -x[1])
    scores = {p.id: s for p, s in ranked}

    sections: list[InterestSection] = []
    shown: set[str] = set()
    for interest in req.interests:
        matches = [(p, s) for p, s in ranked if interest in p.categories]
        if not matches:
            continue
        picks = matches[:PER_SECTION]
        shown.update(p.id for p, _ in picks)
        sections.append(InterestSection(
            interest=interest,
            label=CATEGORIES[interest],
            headline=f"اگر در {city.name} دنبال {PHRASES[interest]} هستی",
            places=[_suggest(p, req, city, s, interest, i) for i, (p, s) in enumerate(picks)],
        ))

    must_see = [(p, s) for p, s in ranked if p.popularity == 3 and p.id not in shown][:MUST_SEE]

    # The itinerary covers the interest picks first, then famous places, then the rest by score.
    priority = {pid: 0 for pid in shown} | {p.id: 1 for p, _ in must_see}
    ordered = sorted(ranked, key=lambda x: (priority.get(x[0].id, 2), -x[1]))
    if req.interests:
        ordered = [(p, s) for p, s in ordered
                   if p.id in priority or set(req.interests) & set(p.categories)]
    days, left = build_days(ordered, req)

    itinerary = []
    for i, places in enumerate(days):
        if not places:
            title = "روز آزاد: استراحت یا تکرار جاهای مورد علاقه"
        elif places[0].trip != "city":
            title = f"سفر یک‌روزه به {places[0].area}" if places[0].trip == "full_day" else f"نیم‌روز در {places[0].area}"
        else:
            areas = [a for a in dict.fromkeys(p.area for p in places) if a != city.name]
            title = "، ".join(areas[:2]) if areas else f"گشت در {city.name}"
        itinerary.append(GuideDay(
            day=i + 1, title=title, hours=sum(_place_hours(p) for p in places),
            places=[_suggest(p, req, city, scores[p.id], None, j) for j, p in enumerate(places)],
        ))

    tips = list(city.tips)
    if req.season in city.hot_seasons:
        tips.append(f"{SEASONS[req.season]} {city.name} گرم است؛ جاهای سرپوشیده را برای ظهر نگه دارید.")
    if req.season in city.cold_seasons:
        tips.append(f"{SEASONS[req.season]} {city.name} سرد است؛ برنامه‌های فضای باز را کوتاه‌تر در نظر بگیرید.")
    if req.budget == "economy":
        tips.append("بیشتر پیشنهادها رایگان یا ارزان‌اند؛ هزینه اصلی شما غذا و جابه‌جایی است.")
    return GuideResponse(
        city=city.id, city_name=city.name, intro=city.intro, sections=sections,
        must_see=[_suggest(p, req, city, s, None, i) for i, (p, s) in enumerate(must_see)],
        itinerary=itinerary, left_out=[p.name for p in left], foods=city.foods, tips=tips,
        excluded=excluded,
    )


def describe_choices() -> dict:
    return {"groups": GROUPS, "budgets": BUDGETS, "seasons": SEASONS, "categories": CATEGORIES, "paces": PACES}
