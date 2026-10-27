"""ساخت متن پیام کانال (HTML تلگرام)."""
from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from .jalali import fa_digits, to_jalali
from .numbers import fmt_toman
from .scrapers import Quote

TEHRAN = ZoneInfo("Asia/Tehran")
_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
           "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
_WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]


def jalali_stamp(now: datetime) -> str:
    now = now.astimezone(TEHRAN)
    y, m, d = to_jalali(now.date())
    return fa_digits(f"{_WEEKDAYS[now.weekday()]} {d} {_MONTHS[m - 1]} {y} — ساعت {now:%H:%M}")


def _arrow(new: float | None, old: float | None) -> str:
    if not new or not old or new == old:
        return ""
    pct = (new - old) / old * 100
    sign = "🔺" if new > old else "🔻"
    return f" {sign}{fa_digits(f'{abs(pct):.2f}')}٪"


def build_message(quotes: list[Quote], previous: dict | None = None, *, now: datetime | None = None,
                  title: str = "قیمت لحظه‌ای طلای آنلاین", handle: str = "") -> str:
    previous = previous or {}
    now = now or datetime.now(TEHRAN)
    ok = [q for q in quotes if q.ok]
    failed = [q for q in quotes if not q.ok]
    ok.sort(key=lambda q: (q.buy is None, q.buy or 0))

    lines = [f"🟡 <b>{escape(title)}</b>", f"🗓 {jalali_stamp(now)}",
             "💰 هر گرم طلای ۱۸ عیار — تومان", ""]

    for i, q in enumerate(ok, 1):
        old_buy, old_sell = previous.get(q.key, (None, None))
        lines.append(f"{fa_digits(i)}. <b>{escape(q.name)}</b>")
        lines.append(f"   🛒 خرید: <code>{fmt_toman(q.buy)}</code>{_arrow(q.buy, old_buy)}")
        lines.append(f"   💵 فروش: <code>{fmt_toman(q.sell)}</code>{_arrow(q.sell, old_sell)}")
        if q.spread is not None:
            lines.append(f"   ↔️ اختلاف: {fa_digits(f'{q.spread:.2f}')}٪")
        lines.append("")

    buys = [q for q in ok if q.buy]
    sells = [q for q in ok if q.sell]
    if buys:
        best = min(buys, key=lambda q: q.buy)
        lines.append(f"✅ ارزان‌ترین خرید: <b>{escape(best.name)}</b> ({fmt_toman(best.buy)})")
    if sells:
        best = max(sells, key=lambda q: q.sell)
        lines.append(f"✅ بهترین فروش: <b>{escape(best.name)}</b> ({fmt_toman(best.sell)})")
    if failed:
        lines.append("")
        lines.append("⚠️ در دسترس نبود: " + "، ".join(escape(q.name) for q in failed))
    if not ok:
        lines.append("هیچ قیمتی دریافت نشد.")
    if handle:
        lines += ["", escape(handle)]
    return "\n".join(lines).strip()


def prices_changed(quotes: list[Quote], previous: dict) -> bool:
    for q in quotes:
        if q.ok and previous.get(q.key) != (q.buy, q.sell):
            return True
    return False
