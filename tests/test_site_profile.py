from app.models import PlanRequest, Risk
from app.site_profile import NEW_SITE_ANCHORS, assess, site_stage


def req(profile=None, **kw):
    base = dict(site_url="https://shop.ir", budget=80_000_000, months=3, category="ecommerce",
                keywords=[{"keyword": "خرید گوشی", "url": "https://shop.ir/m"}], profile=profile or {})
    base.update(kw)
    return PlanRequest(**base)


def test_stage_detection():
    assert site_stage(req().profile) == "unknown"
    assert site_stage(req({"domain_age_years": 0.5, "authority": 30}).profile) == "new"
    assert site_stage(req({"authority": 20, "domain_age_years": 3}).profile) == "growing"
    assert site_stage(req({"authority": 45}).profile) == "established"


def test_new_site_is_slow_brand_heavy_and_ramped():
    a = assess(req({"domain_age_years": 0.4}))
    assert a.monthly_cap == 4 and a.ramp_up and a.anchor_mix == NEW_SITE_ANCHORS
    assert a.type_multipliers["news_agency"] < 1 < a.type_multipliers["blog"]


def test_penalty_forces_conservative():
    a = assess(req({"penalty_history": True, "authority": 25}, risk="aggressive"))
    assert a.risk == Risk.conservative and a.monthly_cap == 4


def test_established_with_steady_links_gets_higher_cap():
    a = assess(req({"authority": 50, "recent_links": "many"}))
    assert a.monthly_cap == 15  # 8 * 1.5 * 1.25


def test_keyword_heavy_history_drops_exact_anchors():
    a = assess(req({"authority": 25, "anchor_history": "keyword_heavy"}))
    assert a.anchor_mix["exact"] == 0


def test_competitor_gap_and_local_scope():
    a = assess(req({"authority": 15, "competitor_authority": 45, "scope": "local"}, months=3))
    assert a.authority_boost > 0 and a.type_multipliers["directory"] == 2
    assert any("۶ ماهه" in w for w in a.warnings)


def test_plan_reflects_new_site_profile(client, plan_request):
    plan_request["profile"] = {"domain_age_years": 0.3, "authority": 5}
    data = client.post("/api/plan", json=plan_request).json()
    sa = data["site_assessment"]
    assert sa["stage"] == "new" and sa["monthly_cap"] == 4 and sa["adjustments"]
    for s in data["scenarios"]:
        assert s["item_count"] <= 4 * 3
        assert all(it["anchor_type"] != "exact" for it in s["items"])
        # ramp-up: every first-month link is weaker than every last-month link
        power = lambda it: it["quality"] * (1 + it["authority"] / 20)  # noqa: E731
        first = [power(it) for it in s["items"] if it["month"] == 1]
        last = [power(it) for it in s["items"] if it["month"] == 3]
        if first and last:
            assert max(first) <= min(last) + 1e-6


def test_plan_without_profile_warns_unknown(client, plan_request):
    data = client.post("/api/plan", json=plan_request).json()
    assert data["site_assessment"]["stage"] == "unknown" and data["site_assessment"]["warnings"]
