def test_index_and_meta(client):
    assert "لینک" in client.get("/").text
    meta = client.get("/api/meta").json()
    assert "ecommerce" in meta["categories"] and "balanced" in meta["risks"]


def test_plan_scenarios_within_budget(client, plan_request):
    res = client.post("/api/plan", json=plan_request)
    assert res.status_code == 200
    data = res.json()
    assert [s["key"] for s in data["scenarios"]] == ["economy", "balanced", "power"]
    for s in data["scenarios"]:
        assert 0 < s["total_cost"] <= s["budget"] <= plan_request["budget"]
        assert s["item_count"] <= 8 * plan_request["months"]  # balanced risk velocity cap
        domains = [it["domain"] for it in s["items"]]
        assert len(domains) == len(set(domains))
        assert all(1 <= it["month"] <= 3 for it in s["items"])
        assert sum(m["count"] for m in s["monthly"]) == s["item_count"]
    balanced = data["scenarios"][1]
    assert balanced["total_cost"] >= 0.9 * plan_request["budget"]
    brand_items = [it for it in balanced["items"] if it["anchor_type"] == "brand"]
    assert brand_items and all(it["anchor_text"] == "دیجی‌شاپ" for it in brand_items)
    assert all(it["target_url"] == "https://www.digishop.ir/" for it in brand_items)


def test_plan_filters_applied(client, plan_request):
    plan_request.update(dofollow_only=True, permanent_only=True, allowed_types=["niche", "blog"])
    data = client.post("/api/plan", json=plan_request).json()
    for s in data["scenarios"]:
        for it in s["items"]:
            assert it["link_type"] == "dofollow" and it["permanent"]
            assert it["type"] in {"niche", "blog"}


def test_tiny_budget_warns(client, plan_request):
    plan_request["budget"] = 10_000
    data = client.post("/api/plan", json=plan_request).json()
    assert all(s["item_count"] == 0 and s["warnings"] for s in data["scenarios"])


def test_plan_validation(client, plan_request):
    plan_request["category"] = "nope"
    assert client.post("/api/plan", json=plan_request).status_code == 422
    plan_request.update(category="ecommerce", keywords=[])
    assert client.post("/api/plan", json=plan_request).status_code == 422


def test_publisher_import_replace_and_reject(client):
    csv_text = client.get("/api/publishers.csv").text.lstrip("﻿")
    header, first = csv_text.splitlines()[:2]
    res = client.post("/api/publishers/import", content="\n".join([header, first]).encode())
    assert res.status_code == 200 and res.json() == {"imported": 1}
    assert len(client.get("/api/publishers").json()) == 1

    bad = client.post("/api/publishers/import", content=b"id,name\n1,x\n")
    assert bad.status_code == 400
    assert len(client.get("/api/publishers").json()) == 1
