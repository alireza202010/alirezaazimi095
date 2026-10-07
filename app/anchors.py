"""Anchor text distribution, anchor text and content brief suggestions."""

from urllib.parse import urlparse

from app.jalali import fa_digits
from app.models import Risk

ANCHOR_MIX: dict[Risk, dict[str, float]] = {
    Risk.conservative: {"brand": 0.45, "naked": 0.25, "generic": 0.15, "partial": 0.10, "exact": 0.05},
    Risk.balanced: {"brand": 0.40, "naked": 0.20, "generic": 0.15, "partial": 0.15, "exact": 0.10},
    Risk.aggressive: {"brand": 0.30, "naked": 0.15, "generic": 0.10, "partial": 0.25, "exact": 0.20},
}

GENERIC_ANCHORS = ["این سایت", "وب‌سایت رسمی", "اطلاعات بیشتر", "اینجا", "مشاهده جزئیات"]
PARTIAL_TEMPLATES = ["بهترین {kw}", "راهنمای {kw}", "{kw} با بهترین قیمت", "مرجع تخصصی {kw}", "{kw} معتبر"]
BRIEF_TEMPLATES = [
    "راهنمای کامل {kw} در سال {year}",
    "معرفی {brand}؛ انتخابی مطمئن برای {kw}",
    "۷ نکته مهم پیش از انتخاب {kw}",
    "مقایسه بهترین گزینه‌های {kw} و نکات خرید",
    "چرا {kw} اهمیت دارد؟ بررسی بازار و پیشنهادهای کاربردی",
    "تجربه کاربران از {kw}: آنچه باید بدانید",
]
NEWS_BRIEF_TEMPLATES = [
    "{brand} خدمات جدید خود در حوزه {kw} را معرفی کرد",
    "رشد بازار {kw} و نقش {brand} در آن",
    "گفت‌وگو با مدیر {brand} درباره آینده {kw}",
]


def allocate(n: int, mix: dict[str, float]) -> list[str]:
    """Largest-remainder allocation of n anchors, interleaved so types are spread out."""
    if n <= 0:
        return []
    raw = {k: v * n for k, v in mix.items()}
    counts = {k: int(v) for k, v in raw.items()}
    leftover = n - sum(counts.values())
    for k in sorted(raw, key=lambda k: raw[k] - counts[k], reverse=True)[:leftover]:
        counts[k] += 1

    order: list[str] = []
    remaining = dict(counts)
    while len(order) < n:
        for k in mix:
            if remaining[k] > 0:
                order.append(k)
                remaining[k] -= 1
    return order


def domain_of(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc or parsed.path
    return host.lower().removeprefix("www.").rstrip("/")


def homepage_of(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return f"{parsed.scheme or 'https'}://{parsed.netloc or parsed.path.rstrip('/')}/"


def anchor_text(anchor_type: str, keyword: str, brand: str, site_domain: str, i: int) -> str:
    if anchor_type == "brand":
        return brand
    if anchor_type == "naked":
        return site_domain
    if anchor_type == "generic":
        return GENERIC_ANCHORS[i % len(GENERIC_ANCHORS)]
    if anchor_type == "partial":
        return PARTIAL_TEMPLATES[i % len(PARTIAL_TEMPLATES)].format(kw=keyword)
    return keyword


def brief_title(publisher_type: str, keyword: str, brand: str, year: int, i: int) -> str:
    templates = NEWS_BRIEF_TEMPLATES if publisher_type in {"news_agency", "news"} else BRIEF_TEMPLATES
    return templates[i % len(templates)].format(kw=keyword, brand=brand, year=fa_digits(year))
