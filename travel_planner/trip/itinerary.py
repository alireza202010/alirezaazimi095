"""Day-by-day itinerary from a destination's attractions and the traveler's interests."""

from trip.catalog import JALALI_MONTHS
from trip.costs import trip_dates
from trip.jalali import fa_digits, to_jalali
from trip.models import DayPlan, Destination, TripRequest

WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]


def date_label(d) -> str:
    _, jm, jd = to_jalali(d)
    return f"{WEEKDAYS[d.weekday()]} {fa_digits(jd)} {JALALI_MONTHS[jm - 1]}"


def build_itinerary(dest: Destination, req: TripRequest) -> list[DayPlan]:
    dates = trip_dates(req)
    n = len(dates)
    # Interest matches first, in the user's order of interests; otherwise keep the curated order.
    rank = {tag: i for i, tag in enumerate(req.interests)}
    queue = sorted(dest.attractions, key=lambda a: rank.get(a.tag, len(rank)))
    # Keep one shopping stop for the last day when possible.
    last_day_stop = next((a for a in reversed(queue) if a.tag == "shopping"), None)
    if last_day_stop and n > 2:
        queue.remove(last_day_stop)
    else:
        last_day_stop = None

    capacity = [2, 1] if n == 2 else [1] + [2] * (n - 2) + [1]
    plans: list[DayPlan] = []
    for i, (d, slots) in enumerate(zip(dates, capacity)):
        picked = [queue.pop(0).name for _ in range(min(slots, len(queue)))]
        if i == 0:
            title = "ورود و استقرار"
            activities = ["رسیدن به مقصد و تحویل اتاق"] + picked
        elif i == n - 1:
            title = "بازگشت"
            extra = [last_day_stop.name] if last_day_stop else (picked or ["گشت آزاد و خرید سوغات"])
            activities = extra + ["حرکت به سمت مبدأ"]
        else:
            title = f"روز {fa_digits(i + 1)}"
            activities = picked or ["روز آزاد: استراحت یا بازدید دوباره از جاهای مورد علاقه"]
        plans.append(DayPlan(day=i + 1, date_label=date_label(d), title=title, activities=activities))
    return plans
