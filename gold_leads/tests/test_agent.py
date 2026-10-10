from conftest import FakeHttp, FakeHTTPError

from leadgen.agent import Config, LeadAgent
from leadgen.export import read_xlsx
from leadgen.table import ALL_TAB


def handler(method, url, kwargs):
    if "places.googleapis.com" in url:
        return {"places": [{
            "id": "g1", "displayName": {"text": "گالری طلای کیان"}, "types": ["jewelry_store"],
            "formattedAddress": "تهران، خیابان ۱۵ خرداد، بازار طلا", "location": {"latitude": 35.6745, "longitude": 51.4210},
            "nationalPhoneNumber": "021 5566 7788", "rating": 4.6, "userRatingCount": 300,
        }]}
    if "api.neshan.org/v3/search" in url:
        return {"items": [
            {"title": "طلا و جواهر کیان", "location": {"x": 51.42105, "y": 35.67455}, "neighbourhood": "بازار"},
            {"title": "طلافروشی ونک", "location": {"x": 51.41, "y": 35.757}, "address": "میدان ونک"},
        ]}
    if "api.neshan.org/v5/reverse" in url:
        zone = "12" if kwargs["params"]["lat"] < 35.7 else "3"
        return {"municipality_zone": zone, "city": "تهران"}
    if "overpass" in url:
        return {"elements": []}
    raise AssertionError(url)


class FakeSheet:
    def __init__(self):
        self.tabs = {}

    def read_tabs(self):
        return self.tabs

    def write_tabs(self, tabs):
        self.tabs = tabs
        return "https://docs.google.com/spreadsheets/d/x"


def test_full_run_writes_sheet_and_excel(tmp_path):
    cfg = Config(neshan_key="n", google_key="g", sheet_id="x", grid_step=0.2,
                 cache_dir=tmp_path / "cache", out_dir=tmp_path / "out", districts_file=tmp_path / "none.json")
    sheet = FakeSheet()
    agent = LeadAgent(cfg, http=FakeHttp(handler), sheet=sheet)

    report = agent.run()
    assert report["unique_shops"] == 2
    assert report["with_phone"] == 1
    assert report["districts_covered"] == 2 and report["unknown_district"] == 0
    assert {"منطقه ۳", "منطقه ۱۲"} <= set(sheet.tabs)
    xlsx_tabs = read_xlsx(tmp_path / "out" / "tehran_gold_leads.xlsx")
    assert len(xlsx_tabs[ALL_TAB]) == 3
    assert (tmp_path / "out" / "tehran_gold_leads.csv").exists()


def test_check_keys_reports_each_service(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def check_handler(method, url, kwargs):
        if "/v5/reverse" in url:
            return {"formatted_address": "تهران، بازار", "municipality_zone": "12"}
        raise FakeHTTPError(403)  # key has no search access

    cfg = Config(neshan_key="service.x", cache_dir=tmp_path, out_dir=tmp_path)
    results = {name: (ok, detail) for name, ok, detail in LeadAgent(cfg, http=FakeHttp(check_handler)).check_keys()}
    assert results["Neshan reverse geocoding (district)"][0] is True
    assert "municipality_zone=12" in results["Neshan reverse geocoding (district)"][1]
    assert results["Neshan search"][0] is False and "Search API" in results["Neshan search"][1]
    assert results["Map.ir search"] == (None, "not set")


def test_env_file_is_loaded_without_overriding(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# keys\nNESHAN_API_KEY="service.abc"\nexport MAPIR_API_KEY=m1\nGOOGLE_SHEET_ID=from-file\n')
    monkeypatch.delenv("NESHAN_API_KEY", raising=False)
    monkeypatch.delenv("MAPIR_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_SHEET_ID", "from-env")
    cfg = Config.from_env(env_file=env)
    assert (cfg.neshan_key, cfg.mapir_key, cfg.sheet_id) == ("service.abc", "m1", "from-env")


def test_missing_keys_skip_sources(tmp_path):
    cfg = Config(sources=["google", "neshan", "osm"], cache_dir=tmp_path, out_dir=tmp_path)
    names = [s.name for s in LeadAgent(cfg, http=FakeHttp(handler)).build_sources()]
    assert names == ["osm"]
