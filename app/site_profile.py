"""Turns what we know about the client's site into concrete plan adjustments."""

from dataclasses import dataclass, field

from app.anchors import ANCHOR_MIX
from app.models import AnchorHistory, PlanRequest, RecentLinks, Risk, SiteProfile, SiteScope

# Natural link velocity: maximum new links per month before site-specific adjustment.
MONTHLY_CAP = {Risk.conservative: 4, Risk.balanced: 8, Risk.aggressive: 15}
MAX_MONTHLY_CAP = 25

STAGE_LABELS = {
    "new": "نوپا",
    "growing": "در حال رشد",
    "established": "معتبر و جاافتاده",
    "unknown": "نامشخص",
}

# Young sites: mostly brand/URL anchors, no exact-match.
NEW_SITE_ANCHORS = {"brand": 0.50, "naked": 0.25, "generic": 0.15, "partial": 0.10, "exact": 0.0}
# Over-optimized profiles: dilute with brand/URL/generic anchors only.
DILUTION_ANCHORS = {"brand": 0.50, "naked": 0.25, "generic": 0.20, "partial": 0.05, "exact": 0.0}


@dataclass
class Assessment:
    stage: str
    risk: Risk
    monthly_cap: int
    anchor_mix: dict[str, float]
    type_multipliers: dict[str, float] = field(default_factory=dict)
    authority_boost: float = 0.0
    ramp_up: bool = False
    adjustments: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def site_stage(p: SiteProfile) -> str:
    signals = (p.authority, p.domain_age_years, p.referring_domains, p.monthly_organic_traffic)
    if all(v is None for v in signals):
        return "unknown"
    if (
        (p.domain_age_years is not None and p.domain_age_years < 1)
        or (p.authority is not None and p.authority < 10)
        or (p.referring_domains is not None and p.referring_domains < 15)
    ):
        return "new"
    if (
        (p.authority is not None and p.authority >= 35)
        or (p.referring_domains or 0) >= 300
        or (p.monthly_organic_traffic or 0) >= 100_000
    ):
        return "established"
    return "growing"


def assess(req: PlanRequest) -> Assessment:
    p = req.profile
    risk = req.risk
    adjustments: list[str] = []
    warnings: list[str] = []

    if p.penalty_history and risk != Risk.conservative:
        risk = Risk.conservative
        adjustments.append(
            "به‌دلیل سابقه پنالتی یا افت شدید ترافیک، استراتژی محافظه‌کار اعمال شد و ناشران پرریسک حذف شدند."
        )

    stage = site_stage(p)
    a = Assessment(stage=stage, risk=risk, monthly_cap=MONTHLY_CAP[risk], anchor_mix=ANCHOR_MIX[risk])
    multiplier = 1.0

    if stage == "new":
        multiplier *= 0.5
        a.ramp_up = True
        a.anchor_mix = NEW_SITE_ANCHORS
        a.type_multipliers = {"news_agency": 0.3, "news": 0.7, "niche": 1.2, "blog": 1.5, "directory": 1.5}
        adjustments += [
            "سایت شما نوپاست: سقف لینک ماهانه نصف شد تا رشد لینک‌ها طبیعی بماند.",
            "سهم سایت‌های تخصصی، وبلاگ‌ها و دایرکتوری‌ها بیشتر و سهم خبرگزاری‌ها کمتر شد (ساخت پایه پروفایل لینک).",
            "انکرتکست‌ها عمدتاً برند و آدرس سایت هستند و انکر دقیق استفاده نمی‌شود.",
        ]
    elif stage == "established":
        multiplier *= 1.5
        a.type_multipliers = {"news_agency": 1.3, "news": 1.2}
        adjustments.append(
            "سایت شما اعتبار خوبی دارد: سقف لینک ماهانه بیشتر شد و سهم خبرگزاری‌ها و سایت‌های قوی افزایش یافت."
        )
    elif stage == "unknown":
        warnings.append(
            "اطلاعات کافی از وضعیت سایت نداریم و پلن با فرض «در حال رشد» ساخته شد. "
            "با تحلیل سایت و پاسخ به سؤال‌ها پلن دقیق‌تر می‌شود."
        )

    if p.recent_links == RecentLinks.none and stage != "new":
        multiplier *= 0.75
        a.ramp_up = True
        adjustments.append(
            "در ۶ ماه اخیر لینکی نگرفته‌اید؛ برای جلوگیری از جهش ناگهانی، شروع ملایم و تدریجی در نظر گرفته شد."
        )
    elif p.recent_links == RecentLinks.many:
        multiplier *= 1.25
        adjustments.append("سابقه لینک‌سازی مستمر دارید؛ سقف لینک ماهانه کمی بیشتر شد.")

    if p.anchor_history == AnchorHistory.keyword_heavy:
        a.anchor_mix = DILUTION_ANCHORS
        adjustments.append(
            "انکرتکست‌های فعلی‌تان پر از کلمه کلیدی است؛ در این پلن انکر دقیق استفاده نمی‌شود "
            "و تمرکز روی برند و آدرس سایت است تا پروفایل طبیعی شود."
        )

    if p.competitor_authority is not None and p.authority is not None:
        gap = p.competitor_authority - p.authority
        if gap >= 20:
            a.authority_boost = 0.1
            adjustments.append(
                f"اعتبار رقبا حدود {gap} واحد بیشتر از شماست؛ وزن اعتبار دامنه ناشران در انتخاب‌ها بیشتر شد."
            )
            if req.months < 6:
                warnings.append(
                    "برای جبران فاصله با رقبا، کمپین ۶ ماهه یا بیشتر و تمرکز اولیه روی کلمات کم‌رقابت‌تر پیشنهاد می‌شود."
                )

    if p.scope == SiteScope.local:
        a.type_multipliers["directory"] = a.type_multipliers.get("directory", 1.0) * 2
        adjustments.append(
            "کسب‌وکار محلی: سهم دایرکتوری‌ها و نیازمندی‌ها بیشتر شد. "
            "ثبت در Google Business Profile و نقشه‌های داخلی (نشان، بلد) را هم انجام دهید."
        )

    if p.indexed_pages is not None and p.indexed_pages < 20:
        warnings.append("تعداد صفحات ایندکس‌شده سایت کم است؛ پیش از لینک‌سازی سنگین، محتوای بیشتری منتشر کنید.")
    if (
        p.authority is not None and p.monthly_organic_traffic is not None
        and p.authority >= 30 and p.monthly_organic_traffic < 1000
    ):
        warnings.append(
            "اعتبار دامنه بالا ولی ترافیک ارگانیک بسیار کم است؛ احتمال مشکل فنی، محتوایی یا پنالتی را بررسی کنید."
        )

    a.monthly_cap = min(MAX_MONTHLY_CAP, max(2, round(MONTHLY_CAP[risk] * multiplier)))
    a.adjustments = adjustments
    a.warnings = warnings
    return a
