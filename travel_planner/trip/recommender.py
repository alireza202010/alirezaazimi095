"""Scores and ranks destinations for a trip request."""

from collections import Counter

from trip.catalog import COMFORT_LEVELS, INTERESTS, TRANSPORT_MODES, TRAVELER_TYPES, VISA_TYPES
from trip.costs import estimate, overlaps_nowruz, season_score
from trip.itinerary import build_itinerary
from trip.jalali import fa_digits
from trip.models import Comfort, Destination, Recommendation, Scope, TripRequest, TripResponse

TIERS_BEST_FIRST = ["luxury", "standard", "economy"]
COMFORT_VALUE = {"economy": 0.6, "standard": 0.85, "luxury": 1.0}
OVER_BUDGET_TOLERANCE = 1.10
MIN_SEASON = 1.6
MIN_INTEREST = 0.15
NO_INTEREST_DEFAULT = 0.6

WEIGHTS = {"interest": 0.40, "season": 0.25, "budget": 0.15, "duration": 0.10, "traveler": 0.10}


def interest_score(dest: Destination, interests: list[str]) -> float:
    if not interests:
        return NO_INTEREST_DEFAULT
    return sum(dest.tags.get(i, 0.0) for i in interests) / len(interests)


def duration_fit(dest: Destination, days: int) -> float:
    if days <= dest.max_days:
        return 1.0
    return max(0.5, 1 - 0.08 * (days - dest.max_days))


def season_label(score: float) -> str:
    if score >= 4.5:
        return "فصل عالی"
    if score >= 3.5:
        return "فصل خوب"
    if score >= 2.5:
        return "قابل قبول"
    return "فصل نامناسب"


def exclusion_reason(dest: Destination, req: TripRequest) -> str | None:
    if req.scope != Scope.both and dest.scope != req.scope:
        return "خارج از محدوده داخلی/خارجی انتخابی"
    if req.visa_free_only and dest.visa not in {"domestic", "free", "on_arrival"}:
        return "نیاز به ویزای قبلی"
    if req.max_travel_hours is not None and dest.travel_hours > req.max_travel_hours:
        return "مسیر طولانی‌تر از حد انتخابی"
    if req.days < dest.min_days:
        return "مدت سفر برای این مقصد کوتاه است"
    if season_score(dest, req) < MIN_SEASON:
        return "آب‌وهوای نامناسب در تاریخ سفر"
    if req.interests and interest_score(dest, req.interests) < MIN_INTEREST:
        return "هم‌خوانی کم با علایق شما"
    return None


def _pct(x: float) -> str:
    return fa_digits(round(x * 100))


def recommend(req: TripRequest, destinations: list[Destination]) -> TripResponse:
    nowruz = overlaps_nowruz(req)
    tiers = TIERS_BEST_FIRST if req.comfort == Comfort.auto else [req.comfort.value]
    excluded: Counter[str] = Counter()
    over_budget: list[tuple[int, Destination]] = []
    results: list[Recommendation] = []

    for dest in destinations:
        reason = exclusion_reason(dest, req)
        if reason:
            excluded[reason] += 1
            continue

        chosen = None
        for tier in tiers:
            cost = estimate(dest, req, tier, nowruz)
            if cost.total <= req.budget:
                chosen = (tier, cost, False)
                break
        if chosen is None:
            if cost.total <= req.budget * OVER_BUDGET_TOLERANCE:
                chosen = (tiers[-1], cost, True)
            else:
                excluded["بیشتر از بودجه"] += 1
                over_budget.append((cost.total, dest))
                continue
        tier, cost, over = chosen

        interest = interest_score(dest, req.interests)
        season = season_score(dest, req)
        duration = duration_fit(dest, req.days)
        traveler = 1.0 if req.traveler_type in dest.good_for else 0.6
        budget_value = 0.3 if over else COMFORT_VALUE[tier]
        score = 100 * (
            WEIGHTS["interest"] * interest
            + WEIGHTS["season"] * (season - 1) / 4
            + WEIGHTS["budget"] * budget_value
            + WEIGHTS["duration"] * duration
            + WEIGHTS["traveler"] * traveler
        )

        reasons: list[str] = []
        matched = [INTERESTS[i] for i in req.interests if dest.tags.get(i, 0) >= 0.7]
        if matched:
            reasons.append("مناسب برای علاقه‌های شما: " + "، ".join(matched))
        if season >= 3.5:
            reasons.append(f"آب‌وهوای مناسب در تاریخ سفر ({season_label(season)})")
        if not over:
            reasons.append(f"با بودجه شما سفر در سطح «{COMFORT_LEVELS[tier]}» ممکن است")
        if dest.visa in {"domestic", "free", "on_arrival"}:
            reasons.append(VISA_TYPES[dest.visa])
        if dest.travel_hours <= 2.5:
            reasons.append(f"مسیر کوتاه (حدود {fa_digits(dest.travel_hours)} ساعت)")
        if req.traveler_type in dest.good_for:
            reasons.append(f"مناسب سفر {TRAVELER_TYPES[req.traveler_type]}")
        if not over and cost.total <= req.budget * 0.6 and (tier == "luxury" or req.comfort != Comfort.auto):
            reasons.append(f"فقط حدود {_pct(cost.total / req.budget)}٪ بودجه؛ می‌توانید روزها را بیشتر کنید")

        warnings: list[str] = []
        if over:
            warnings.append(f"حدود {_pct(cost.total / req.budget - 1)}٪ بیشتر از بودجه شما")
        if season < 2.5:
            warnings.append("آب‌وهوا در تاریخ سفر ایده‌آل نیست")
        if req.days > dest.max_days:
            warnings.append(
                f"برای این مقصد {fa_digits(dest.max_days)} روز کافی است؛ می‌توانید آن را با مقصد دیگری ترکیب کنید"
            )
        if dest.visa == "embassy":
            warnings.append("ویزای سفارت چند هفته تا چند ماه زمان می‌برد؛ زود اقدام کنید")
        elif dest.visa == "required":
            warnings.append("قبل از رزرو، شرایط و زمان صدور ویزا را بررسی کنید")
        if nowruz:
            warnings.append("سفر در نوروز: قیمت‌ها بالاتر است و باید زودتر رزرو کنید")
        if req.traveler_type == "family" and "family" not in dest.good_for:
            warnings.append("برای سفر با کودک ایده‌آل نیست")

        results.append(Recommendation(
            id=dest.id,
            name=dest.name,
            country=dest.country,
            scope=dest.scope.value,
            summary=dest.summary,
            score=round(score, 1),
            comfort=tier,
            comfort_label=COMFORT_LEVELS[tier],
            over_budget=over,
            cost=cost,
            visa=dest.visa,
            visa_label=VISA_TYPES[dest.visa],
            transport_label=TRANSPORT_MODES[dest.transport_mode],
            travel_hours=dest.travel_hours,
            season_score=season,
            season_label=season_label(season),
            reasons=reasons,
            warnings=warnings,
            attractions=[a.name for a in dest.attractions],
            itinerary=build_itinerary(dest, req),
            tips=dest.tips,
        ))

    results.sort(key=lambda r: (r.over_budget, -r.score))
    over_budget.sort(key=lambda x: x[0])
    return TripResponse(
        nights=req.nights,
        days=req.days,
        travelers=req.adults + req.children,
        nowruz=nowruz,
        considered=len(destinations),
        excluded=dict(excluded),
        recommendations=results[: req.limit],
        cheapest_excluded=[{"name": d.name, "country": d.country, "total": t} for t, d in over_budget[:3]],
        notes=[
            "هزینه‌ها تخمینی و بر پایه نرخ دلار واردشده است؛ قبل از رزرو قیمت روز را از آژانس یا سایت‌های رزرو بگیرید.",
            "مبدأ سفر تهران در نظر گرفته شده است.",
            "قوانین ویزا برای گذرنامه ایرانی مدام تغییر می‌کند؛ پیش از سفر از سفارت یا آژانس معتبر استعلام کنید.",
        ],
    )
