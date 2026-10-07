def test_index_and_meta(client):
    assert client.get("/").status_code == 200
    meta = client.get("/api/meta").json()
    assert "history" in meta["interests"] and meta["default_usd_rate"] > 0
    assert len(client.get("/api/destinations").json()) >= 35


def test_recommendations_fit_budget_and_are_ranked(client, trip):
    d = client.post("/api/recommend", json=trip).json()
    recs = d["recommendations"]
    assert recs and d["nights"] == 5 and d["travelers"] == 2
    in_budget = [r for r in recs if not r["over_budget"]]
    assert all(r["cost"]["total"] <= trip["budget"] for r in in_budget)
    assert all(r["cost"]["total"] <= trip["budget"] * 1.1 for r in recs)
    scores = [r["score"] for r in in_budget]
    assert scores == sorted(scores, reverse=True)
    top = recs[0]
    assert top["reasons"] and len(top["itinerary"]) == 6
    assert sum(d["excluded"].values()) + len(recs) <= d["considered"]


def test_domestic_visa_free_scope(client, trip):
    trip.update(scope="domestic")
    for r in client.post("/api/recommend", json=trip).json()["recommendations"]:
        assert r["scope"] == "domestic" and r["visa"] == "domestic"
    trip.update(scope="international", visa_free_only=True, budget=500_000_000)
    recs = client.post("/api/recommend", json=trip).json()["recommendations"]
    assert recs and all(r["visa"] in {"free", "on_arrival"} for r in recs)


def test_fixed_comfort_and_tiny_budget(client, trip):
    trip.update(comfort="economy")
    assert all(r["comfort"] == "economy" for r in client.post("/api/recommend", json=trip).json()["recommendations"])
    trip.update(budget=1_000_000, comfort="auto")
    d = client.post("/api/recommend", json=trip).json()
    assert d["recommendations"] == [] and d["cheapest_excluded"]
    assert d["cheapest_excluded"][0]["total"] <= d["cheapest_excluded"][-1]["total"]


def test_nowruz_flag_and_seasonal_ranking(client, trip):
    trip.update(start_date="2027-03-20", end_date="2027-03-25", interests=[], budget=400_000_000)
    d = client.post("/api/recommend", json=trip).json()
    assert d["nowruz"] and all(any("نوروز" in w for w in r["warnings"]) for r in d["recommendations"])

    trip.update(start_date="2027-01-10", end_date="2027-01-14", interests=["ski"], nowruz=None)
    trip.pop("nowruz")
    assert client.post("/api/recommend", json=trip).json()["recommendations"][0]["id"] == "dizin"


def test_validation_errors(client, trip):
    assert client.post("/api/recommend", json={**trip, "end_date": "2026-11-01"}).status_code == 422
    assert client.post("/api/recommend", json={**trip, "traveler_type": "x"}).status_code == 422
    assert client.post("/api/recommend", json={**trip, "usd_rate": 0}).status_code == 422
