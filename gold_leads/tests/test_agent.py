from conftest import FakeHttp

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
    if "api.neshan.org/v1/search" in url:
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


def test_missing_keys_skip_sources(tmp_path):
    cfg = Config(sources=["google", "neshan", "osm"], cache_dir=tmp_path, out_dir=tmp_path)
    names = [s.name for s in LeadAgent(cfg, http=FakeHttp(handler)).build_sources()]
    assert names == ["osm"]
