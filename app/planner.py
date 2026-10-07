"""Builds link-building plan scenarios from a request and the publisher inventory."""

from collections import Counter
from dataclasses import dataclass

from app import anchors
from app.catalog import ANCHOR_TYPES, PRODUCTS, PUBLISHER_TYPES
from app.jalali import current_jalali_year, month_labels
from app.models import MonthSummary, PlanItem, PlanRequest, PlanResponse, Publisher, Risk, Scenario
from app.optimizer import group_knapsack
from app.scoring import Scored, exclusion_reason, score

# Natural link velocity: maximum new links per month.
MONTHLY_CAP = {Risk.conservative: 4, Risk.balanced: 8, Risk.aggressive: 15}


@dataclass(frozen=True)
class ScenarioConfig:
    key: str
    title: str
    description: str
    budget_share: float
    mix: dict[str, float]
    authority_boost: float = 0.0


SCENARIOS = [
    ScenarioConfig(
        "economy", "اقتصادی",
        "حدود ۶۰٪ بودجه؛ تمرکز بر سایت‌های تخصصی ارزان با بیشترین ارزش به ازای هر تومان.",
        0.6, {"niche": 0.5, "news": 0.2, "blog": 0.2, "directory": 0.1},
    ),
    ScenarioConfig(
        "balanced", "متعادل",
        "کل بودجه؛ ترکیب سالم از سایت‌های تخصصی، خبری و خبرگزاری.",
        1.0, {"niche": 0.45, "news": 0.25, "news_agency": 0.2, "blog": 0.05, "directory": 0.05},
    ),
    ScenarioConfig(
        "power", "پرقدرت",
        "کل بودجه؛ وزن بیشتر به اعتبار دامنه و خبرگزاری‌ها برای اثر سریع‌تر و برندینگ.",
        1.0, {"news_agency": 0.35, "news": 0.25, "niche": 0.35, "blog": 0.05},
        authority_boost=0.15,
    ),
]


def _normalized_mix(mix: dict[str, float], allowed: list[str] | None) -> dict[str, float]:
    if allowed:
        mix = {t: w for t, w in mix.items() if t in allowed}
    total = sum(mix.values())
    return {t: w / total for t, w in mix.items()} if total else {}


def _select_once(
    candidates: list[Scored], budget: int, mix: dict[str, float], slot_cost: float
) -> list[Scored]:
    """Fill each publisher-type bucket with its share, then spend leftovers on anything."""
    chosen: list[Scored] = []
    spent = 0
    for ptype, share in mix.items():
        bucket = [c for c in candidates if c.pub.type == ptype]
        picked = group_knapsack(bucket, int(budget * share), slot_cost=slot_cost)
        chosen.extend(picked)
        spent += sum(p.pub.price for p in picked)

    used_domains = {c.pub.domain for c in chosen}
    rest = [c for c in candidates if c.pub.domain not in used_domains]
    chosen.extend(group_knapsack(rest, budget - spent, slot_cost=slot_cost))
    return chosen


def _select(
    candidates: list[Scored], budget: int, mix: dict[str, float], max_links: int
) -> tuple[list[Scored], bool]:
    """Select offers with at most `max_links` links.

    If the unconstrained selection has too many links, binary-search the smallest
    per-link charge that brings the count under the cap (Lagrangian relaxation),
    so the budget shifts to fewer, stronger links instead of being left unspent.
    Returns the selection and whether the cap was binding.
    """
    chosen = _select_once(candidates, budget, mix, 0.0)
    if len(chosen) <= max_links:
        return chosen, False

    lo, hi = 0.0, max((c.power for c in candidates), default=0.0)
    best: list[Scored] = []
    for _ in range(25):
        mid = (lo + hi) / 2
        trial = _select_once(candidates, budget, mix, mid)
        if len(trial) <= max_links:
            best, hi = trial, mid
        else:
            lo = mid
    if len(best) > max_links:  # defensive; the search keeps only feasible results
        best = sorted(best, key=lambda c: c.power, reverse=True)[:max_links]
    return best, True


def _build_items(
    selected: list[Scored], req: PlanRequest, labels: list[str], brand: str, site_domain: str
) -> list[PlanItem]:
    homepage = anchors.homepage_of(req.site_url)
    year = current_jalali_year()
    # Strongest links first so round-robin spreads them evenly across months.
    ordered = sorted(selected, key=lambda s: s.quality, reverse=True)
    anchor_plan = anchors.allocate(len(ordered), anchors.ANCHOR_MIX[req.risk])

    items: list[PlanItem] = []
    for i, (s, a_type) in enumerate(zip(ordered, anchor_plan)):
        kw = req.keywords[i % len(req.keywords)]
        month = i % req.months + 1
        target = homepage if a_type in {"brand", "naked"} else kw.url
        items.append(PlanItem(
            month=month,
            month_label=labels[month - 1],
            publisher_id=s.pub.id,
            publisher_name=s.pub.name,
            domain=s.pub.domain,
            type=s.pub.type,
            type_label=PUBLISHER_TYPES[s.pub.type],
            product=s.pub.product,
            product_label=PRODUCTS[s.pub.product],
            price=s.pub.price,
            link_type=s.pub.link_type,
            permanent=s.pub.permanent,
            authority=s.pub.authority,
            monthly_traffic=s.pub.monthly_traffic,
            quality=s.quality,
            relevance=s.relevance,
            spam_risk=s.spam_risk,
            keyword=kw.keyword,
            target_url=target,
            anchor_type=a_type,
            anchor_type_label=ANCHOR_TYPES[a_type],
            anchor_text=anchors.anchor_text(a_type, kw.keyword, brand, site_domain, i),
            brief_title=anchors.brief_title(s.pub.type, kw.keyword, brand, year, i),
            reasons=s.reasons,
            cautions=s.cautions,
        ))
    items.sort(key=lambda it: (it.month, -it.quality))
    return items


def _scenario(
    cfg: ScenarioConfig, publishers: list[Publisher], req: PlanRequest, brand: str, site_domain: str
) -> Scenario:
    scored = [score(p, req, cfg.authority_boost) for p in publishers]
    candidates = [s for s in scored if exclusion_reason(s, req) is None]
    budget = int(req.budget * cfg.budget_share)
    mix = _normalized_mix(cfg.mix, req.allowed_types)
    max_links = MONTHLY_CAP[req.risk] * req.months
    selected, capped = _select(candidates, budget, mix, max_links)

    warnings: list[str] = []
    if capped:
        warnings.append(
            f"برای طبیعی ماندن سرعت لینک‌سازی، حداکثر {MONTHLY_CAP[req.risk]} لینک در ماه "
            f"({max_links} لینک در کل) در نظر گرفته شد و بودجه به لینک‌های قوی‌تر اختصاص یافت."
        )

    labels = month_labels(req.months)
    items = _build_items(selected, req, labels, brand, site_domain)
    total = sum(it.price for it in items)
    remaining = budget - total

    if not items:
        warnings.append("با این بودجه و فیلترها هیچ گزینه مناسبی پیدا نشد. بودجه را افزایش یا فیلترها را کمتر کنید.")
    elif remaining > budget * 0.2:
        warnings.append(f"{remaining:,} تومان از بودجه این سناریو بدون گزینه مناسب باقی ماند.")
    exact_share = sum(1 for it in items if it.anchor_type == "exact") / len(items) if items else 0
    if exact_share > 0.15:
        warnings.append("سهم انکرتکست دقیق بالاست؛ ریسک الگوی غیرطبیعی وجود دارد.")

    monthly = []
    for m in range(1, req.months + 1):
        month_items = [it for it in items if it.month == m]
        monthly.append(MonthSummary(
            month=m, label=labels[m - 1], count=len(month_items), cost=sum(it.price for it in month_items)
        ))

    return Scenario(
        key=cfg.key,
        title=cfg.title,
        description=cfg.description,
        budget=budget,
        total_cost=total,
        remaining=remaining,
        item_count=len(items),
        avg_quality=round(sum(it.quality for it in items) / len(items), 1) if items else 0.0,
        items=items,
        type_breakdown=dict(Counter(it.type_label for it in items)),
        anchor_breakdown=dict(Counter(it.anchor_type_label for it in items)),
        monthly=monthly,
        warnings=warnings,
    )


def build_plan(req: PlanRequest, publishers: list[Publisher]) -> PlanResponse:
    site_domain = anchors.domain_of(req.site_url)
    brand = (req.brand_name or "").strip() or site_domain.split(".")[0]

    excluded: Counter[str] = Counter()
    eligible = 0
    for p in publishers:
        reason = exclusion_reason(score(p, req), req)
        if reason:
            excluded[reason] += 1
        else:
            eligible += 1

    return PlanResponse(
        total_offers=len(publishers),
        eligible_offers=eligible,
        excluded=dict(excluded),
        scenarios=[_scenario(cfg, publishers, req, brand, site_domain) for cfg in SCENARIOS],
        notes=[
            "پیشنهادها بر اساس داده‌های موجود در دیتابیس ناشران است؛ قبل از خرید، قیمت و شرایط را با ناشر چک کنید.",
            "خرید لینک برای رتبه طبق سیاست‌های گوگل ریسک دارد؛ تنوع منابع، ارتباط موضوعی و محتوای واقعی را رعایت کنید.",
            "هیچ پلنی تضمین رتبه نیست؛ اثر لینک‌ها معمولاً پس از ۴ تا ۱۲ هفته دیده می‌شود.",
        ],
    )
