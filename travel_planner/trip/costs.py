"""Trip cost estimation."""

import math
from datetime import timedelta

from trip.jalali import is_nowruz
from trip.models import CostBreakdown, Destination, TripRequest

CHILD_DAILY_FACTOR = 0.6
CHILD_TRANSPORT_FACTOR = 0.75
CONTINGENCY = 0.10
NOWRUZ_SURGE = 1.35  # transport and lodging prices around Nowruz
PEAK_SEASON_SURGE = 1.15  # lodging in a destination's best months


def rooms_needed(adults: int, children: int) -> int:
    return max(math.ceil(adults / 2), math.ceil((adults + children) / 4), 1)


def trip_dates(req: TripRequest):
    return [req.start_date + timedelta(days=i) for i in range(req.days)]


def overlaps_nowruz(req: TripRequest) -> bool:
    return any(is_nowruz(d) for d in trip_dates(req))


def season_score(dest: Destination, req: TripRequest) -> float:
    dates = trip_dates(req)
    return round(sum(dest.season[d.month - 1] for d in dates) / len(dates), 2)


def estimate(dest: Destination, req: TripRequest, comfort: str, nowruz: bool) -> CostBreakdown:
    rate = req.usd_rate
    surge = NOWRUZ_SURGE if nowruz else 1.0
    lodging_surge = surge * (PEAK_SEASON_SURGE if season_score(dest, req) >= 4.5 else 1.0)
    rooms = rooms_needed(req.adults, req.children)

    transport = dest.transport_usd * (req.adults + CHILD_TRANSPORT_FACTOR * req.children) * surge
    lodging = getattr(dest.lodging_usd, comfort) * rooms * req.nights * lodging_surge
    daily = getattr(dest.daily_usd, comfort) * req.days * (req.adults + CHILD_DAILY_FACTOR * req.children)
    visa = dest.visa_cost_usd * (req.adults + req.children)
    subtotal = transport + lodging + daily + visa
    contingency = subtotal * CONTINGENCY

    def toman(usd: float) -> int:
        return int(round(usd * rate, -4))

    total = toman(subtotal + contingency)
    return CostBreakdown(
        transport=toman(transport),
        lodging=toman(lodging),
        daily=toman(daily),
        visa=toman(visa),
        contingency=toman(contingency),
        total=total,
        per_person=int(round(total / (req.adults + req.children), -4)),
        rooms=rooms,
    )
