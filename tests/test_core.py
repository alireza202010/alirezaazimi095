from datetime import date

from app.anchors import allocate, domain_of, homepage_of
from app.data import CsvImportError, parse_csv, to_csv
from app.jalali import gregorian_to_jalali, month_labels
from app.models import PlanRequest, Publisher
from app.optimizer import group_knapsack
from app.scoring import Scored, exclusion_reason, relevance, score, spam_risk


def pub(**kw) -> Publisher:
    base = dict(
        id="X1", name="n", domain="a.example", type="niche", categories=["ecommerce"],
        product="reportage", price=1_000_000, authority=40, monthly_traffic=100_000,
        outbound_per_month=5, index_rate=0.95, link_type="dofollow", permanent=True,
    )
    base.update(kw)
    return Publisher(**base)


def req(**kw) -> PlanRequest:
    base = dict(site_url="https://shop.ir", budget=10_000_000, months=1, category="ecommerce",
                keywords=[{"keyword": "k", "url": "https://shop.ir/k"}])
    base.update(kw)
    return PlanRequest(**base)


def test_jalali_conversion():
    assert gregorian_to_jalali(2024, 3, 20) == (1403, 1, 1)
    assert gregorian_to_jalali(2026, 10, 7) == (1405, 7, 15)
    assert month_labels(2, date(2026, 10, 7)) == ["آبان ۱۴۰۵", "آذر ۱۴۰۵"]
    assert month_labels(1, date(2027, 3, 1)) == ["فروردین ۱۴۰۶"]


def test_relevance_levels():
    assert relevance(pub(categories=["ecommerce"]), "ecommerce") == 1.0
    assert relevance(pub(categories=["technology"]), "ecommerce") == 0.65
    assert relevance(pub(categories=["general"]), "ecommerce") == 0.45
    assert relevance(pub(categories=["sports"]), "ecommerce") == 0.1


def test_link_farm_has_high_spam_risk():
    healthy = pub()
    farm = pub(authority=90, monthly_traffic=2_000, outbound_per_month=200, index_rate=0.6)
    assert spam_risk(farm) > 0.6 > spam_risk(healthy)
    assert exclusion_reason(score(farm, req()), req()) == "ریسک اسپم بالا"


def test_nofollow_and_temporary_reduce_quality():
    r = req()
    base = score(pub(), r).quality
    assert score(pub(link_type="nofollow"), r).quality < base
    assert score(pub(permanent=False), r).quality < base


def test_filters_exclude():
    assert exclusion_reason(score(pub(link_type="nofollow"), req()), req(dofollow_only=True)) == "لینک فالو نیست"
    assert exclusion_reason(score(pub(permanent=False), req()), req(permanent_only=True)) == "لینک دائمی نیست"
    assert exclusion_reason(score(pub(price=20_000_000), req()), req()) == "گران‌تر از کل بودجه"
    assert exclusion_reason(score(pub(type="blog"), req()), req(allowed_types=["niche"])) == "نوع سایت انتخاب نشده"


def scored(domain, price, quality, authority=40) -> Scored:
    return Scored(pub(id=domain + str(price), domain=domain, price=price, authority=authority), quality, 1.0, 0.0)


def test_knapsack_respects_budget_and_one_per_domain():
    items = [scored("a", 400_000, 50), scored("a", 300_000, 45), scored("b", 500_000, 60), scored("c", 700_000, 90)]
    chosen = group_knapsack(items, 1_000_000)
    assert sum(c.pub.price for c in chosen) <= 1_000_000
    domains = [c.pub.domain for c in chosen]
    assert len(domains) == len(set(domains))
    assert {c.pub.domain for c in chosen} == {"a", "c"}  # a@300k + c@700k beats a@400k + b@500k


def test_knapsack_slot_cost_prefers_fewer_links():
    items = [scored("a", 100_000, 30), scored("b", 100_000, 30), scored("c", 200_000, 55)]
    assert len(group_knapsack(items, 200_000)) == 2
    assert [c.pub.domain for c in group_knapsack(items, 200_000, slot_cost=100)] == ["c"]


def test_anchor_allocation():
    order = allocate(10, {"brand": 0.4, "naked": 0.2, "generic": 0.15, "partial": 0.15, "exact": 0.1})
    assert len(order) == 10
    assert order.count("brand") == 4 and order.count("exact") == 1
    assert order[:2] == ["brand", "naked"]  # interleaved, not clustered


def test_url_helpers():
    assert domain_of("https://www.Shop.ir/a/b") == "shop.ir"
    assert domain_of("shop.ir") == "shop.ir"
    assert homepage_of("https://shop.ir/a") == "https://shop.ir/"


def test_csv_roundtrip_and_errors():
    pubs = [pub(), pub(id="X2", domain="b.example", categories=["home", "lifestyle"])]
    assert parse_csv(to_csv(pubs)) == pubs
    bad = to_csv(pubs).replace("niche", "unknown_type", 1)
    try:
        parse_csv(bad)
    except CsvImportError as exc:
        assert "line 2" in exc.errors[0]
    else:
        raise AssertionError("expected CsvImportError")
