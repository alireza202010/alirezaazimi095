"""Publisher quality scoring: relevance, spam risk and goal-weighted quality."""

import math
from dataclasses import dataclass, field

from app.catalog import RELATED
from app.models import Goal, PlanRequest, Publisher, Risk

# Positive-signal weights per goal: authority, traffic, relevance, index rate.
GOAL_WEIGHTS: dict[Goal, tuple[float, float, float, float]] = {
    Goal.ranking: (0.30, 0.20, 0.35, 0.15),
    Goal.branding: (0.20, 0.40, 0.20, 0.20),
    Goal.traffic: (0.10, 0.50, 0.30, 0.10),
    Goal.local: (0.20, 0.20, 0.45, 0.15),
}

SPAM_PENALTY = {Risk.conservative: 0.60, Risk.balanced: 0.45, Risk.aggressive: 0.30}
SPAM_LIMIT = {Risk.conservative: 0.45, Risk.balanced: 0.60, Risk.aggressive: 0.75}
MIN_RELEVANCE = {Risk.conservative: 0.60, Risk.balanced: 0.45, Risk.aggressive: 0.30}


@dataclass
class Scored:
    pub: Publisher
    quality: float
    relevance: float
    spam_risk: float
    reasons: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)

    @property
    def power(self) -> float:
        """Optimization value: authority is log-scaled, so a strong domain is worth
        several weak ones; quality already folds in relevance and risk."""
        return self.quality * (1 + self.pub.authority / 20)


def relevance(pub: Publisher, category: str) -> float:
    if category in pub.categories:
        return 1.0
    if RELATED.get(category, set()) & set(pub.categories):
        return 0.65
    if "general" in pub.categories or category == "general":
        return 0.45
    return 0.1


def traffic_score(monthly_traffic: int) -> float:
    """Log-scaled traffic in [0, 1]; ~1M monthly visits maps to 1."""
    return min(1.0, math.log10(monthly_traffic + 1) / 6)


def spam_risk(pub: Publisher) -> float:
    """Heuristic in [0, 1]: inflated authority, link-farm volume and poor indexing."""
    inflated = max(0.0, pub.authority / 100 - traffic_score(pub.monthly_traffic))
    volume = min(1.0, pub.outbound_per_month / 60)
    unindexed = 1 - pub.index_rate
    return round(0.4 * inflated + 0.4 * volume + 0.2 * unindexed, 3)


def score(pub: Publisher, req: PlanRequest, authority_boost: float = 0.0) -> Scored:
    w_auth, w_traffic, w_rel, w_index = GOAL_WEIGHTS[req.goal]
    w_auth += authority_boost
    rel = relevance(pub, req.category)
    spam = spam_risk(pub)
    t_score = traffic_score(pub.monthly_traffic)

    positive = (
        w_auth * pub.authority / 100 + w_traffic * t_score + w_rel * rel + w_index * pub.index_rate
    ) / (w_auth + w_traffic + w_rel + w_index)
    value = max(0.0, positive - SPAM_PENALTY[req.risk] * spam)

    reasons: list[str] = []
    cautions: list[str] = []
    if pub.link_type == "nofollow":
        value *= 0.5 if req.goal == Goal.ranking else 0.85
        cautions.append("لینک نوفالو است (اثر مستقیم کمتری روی رتبه دارد)")
    elif pub.link_type == "sponsored":
        value *= 0.75 if req.goal == Goal.ranking else 0.9
        cautions.append("لینک با برچسب sponsored منتشر می‌شود")
    if not pub.permanent:
        value *= 0.7
        cautions.append("لینک موقت است و پس از مدتی حذف می‌شود")
    if spam >= 0.4:
        cautions.append("نشانه‌های ریسک: حجم بالای رپورتاژ یا ترافیک کم نسبت به اعتبار")

    if rel >= 1.0:
        reasons.append("هم‌موضوع با حوزه شما")
    elif rel >= 0.65:
        reasons.append("موضوع مرتبط با حوزه شما")
    if pub.monthly_traffic >= 500_000:
        reasons.append(f"ترافیک واقعی بالا (~{pub.monthly_traffic:,} بازدید ماهانه)")
    if pub.authority >= 60:
        reasons.append("اعتبار دامنه بالا")
    if pub.outbound_per_month <= 10:
        reasons.append("تعداد رپورتاژ ماهانه کم (ارزش لینک رقیق نمی‌شود)")
    if pub.index_rate >= 0.9:
        reasons.append("نرخ ایندکس بالای رپورتاژها")
    if pub.type == "news_agency":
        reasons.append("خبرگزاری شناخته‌شده؛ مناسب اعتبار برند")

    return Scored(pub, round(value * 100, 2), rel, spam, reasons, cautions)


def exclusion_reason(s: Scored, req: PlanRequest) -> str | None:
    """Return a Persian reason if the offer must not be recommended, else None."""
    pub = s.pub
    if req.allowed_types and pub.type not in req.allowed_types:
        return "نوع سایت انتخاب نشده"
    if req.dofollow_only and pub.link_type != "dofollow":
        return "لینک فالو نیست"
    if req.permanent_only and not pub.permanent:
        return "لینک دائمی نیست"
    if pub.price > req.budget:
        return "گران‌تر از کل بودجه"
    if s.relevance < MIN_RELEVANCE[req.risk]:
        return "ارتباط موضوعی کم"
    if s.spam_risk > SPAM_LIMIT[req.risk]:
        return "ریسک اسپم بالا"
    if s.quality <= 0:
        return "کیفیت ناکافی"
    return None
