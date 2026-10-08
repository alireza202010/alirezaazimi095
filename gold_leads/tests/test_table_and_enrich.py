from types import SimpleNamespace

from leadgen.enrich import SUBMIT_TOOL, Enricher
from leadgen.models import Lead
from leadgen.table import ALL_TAB, HEADERS, SUMMARY_TAB, SYNC_TAB, build_tabs

COL = {h: i for i, h in enumerate(HEADERS)}


def _lead(name, district, **kw):
    return Lead(name=name, district=district, lat=35.7, lng=51.4, sources=["neshan"], **kw)


def test_tabs_are_grouped_by_district():
    leads = [_lead("طلای الف", 6, score=40), _lead("طلای ب", 12, score=70), _lead("طلای ج", None)]
    tabs = build_tabs(leads, {}, "2026-10-08")
    assert list(tabs)[:2] == [SUMMARY_TAB, ALL_TAB]
    assert {"منطقه ۶", "منطقه ۱۲", "نامشخص"} <= set(tabs)
    names = [r[COL["نام فروشگاه"]] for r in tabs[ALL_TAB][1:]]
    assert names == ["طلای الف", "طلای ب", "طلای ج"]  # district order, unknown last
    assert all(r[COL["وضعیت"]] == "جدید" for r in tabs[ALL_TAB][1:])
    assert tabs[SUMMARY_TAB][-1][:2] == ["جمع کل", 3]


def test_sales_edits_survive_reruns():
    lead = _lead("طلای الف", 6, landlines=["02133112233"])
    first = build_tabs([lead], {}, "2026-10-01")
    # salesperson edits the main tab, and another edits the district tab
    main = [list(r) for r in first[ALL_TAB]]
    main[1][COL["یادداشت فروش"]] = "فردا تماس"
    district = [list(r) for r in first["منطقه ۶"]]
    district[1][COL["وضعیت"]] = "علاقه‌مند"
    manual = [""] * len(HEADERS)
    manual[COL["شناسه"]], manual[COL["نام فروشگاه"]], manual[COL["منطقه"]] = "manual-1", "طلای دستی", "منطقه ۶"
    main.append(manual)

    existing = {ALL_TAB: main, "منطقه ۶": district, SUMMARY_TAB: first[SUMMARY_TAB], SYNC_TAB: first[SYNC_TAB]}
    second = build_tabs([lead], existing, "2026-10-08")
    rows = second[ALL_TAB][1:]
    row = next(r for r in rows if r[COL["شناسه"]] == lead.lead_id)
    assert row[COL["یادداشت فروش"]] == "فردا تماس"
    assert row[COL["وضعیت"]] == "علاقه‌مند"
    assert row[COL["اولین مشاهده"]] == "2026-10-01" and row[COL["آخرین بروزرسانی"]] == "2026-10-08"
    assert any(r[COL["شناسه"]] == "manual-1" for r in rows)  # hand-added row kept
    assert second[SYNC_TAB][1][1] == "علاقه‌مند"  # new baseline for the next run

    # Next run: the district tab is now stale, the main tab gets a newer status -> main wins.
    main2 = [list(r) for r in second[ALL_TAB]]
    idx = next(i for i, r in enumerate(main2) if r[COL["شناسه"]] == lead.lead_id)
    main2[idx][COL["وضعیت"]] = "مشتری شد"
    third = build_tabs([lead], {ALL_TAB: main2, "منطقه ۶": second["منطقه ۶"], SYNC_TAB: second[SYNC_TAB]}, "2026-10-09")
    row = next(r for r in third[ALL_TAB][1:] if r[COL["شناسه"]] == lead.lead_id)
    assert row[COL["وضعیت"]] == "مشتری شد"


def test_sales_edits_follow_a_lead_whose_id_changed():
    old = _lead("طلای الف", 6, landlines=["02133112233"])
    first = [list(r) for r in build_tabs([old], {}, "2026-10-01")[ALL_TAB]]
    first[1][COL["وضعیت"]] = "مشتری شد"
    new = _lead("طلای الف", 6, landlines=["02133112233"], google_place_id="g9")  # now found on Google too
    rows = build_tabs([new], {ALL_TAB: first}, "2026-10-08")[ALL_TAB][1:]
    assert len(rows) == 1
    assert rows[0][COL["شناسه"]] == "g:g9" and rows[0][COL["وضعیت"]] == "مشتری شد"


def _block(**kw):
    return SimpleNamespace(**kw)


class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)


def _client(responses):
    messages = FakeMessages(responses)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


SUBMIT_INPUT = {
    "found": True,
    "landline_phones": ["۰۲۱-۵۵۶۶۷۷۸۸", "not a phone"],
    "mobile_phones": ["0912 123 4567"],
    "instagram": "@kian.gold",
    "website": "https://kiangold.ir",
    "shop_type": "wholesale",
    "size": "large",
    "branches": 3,
    "sales_note": "پخش عمده در بازار؛ از حجم سفارش‌ها شروع کنید.",
    "evidence_urls": ["https://instagram.com/kian.gold"],
}


def test_enricher_continues_after_pause_and_applies_result(tmp_path):
    client, messages = _client([
        _block(stop_reason="pause_turn", content=[_block(type="server_tool_use", name="web_search")]),
        _block(stop_reason="tool_use", content=[_block(type="tool_use", name=SUBMIT_TOOL, input=SUBMIT_INPUT)]),
    ])
    enricher = Enricher(client=client, cache_file=tmp_path / "enrich.json")
    lead = _lead("طلای کیان", 12)
    assert enricher.enrich([lead], limit=5) == 1
    assert len(messages.requests) == 2
    req = messages.requests[0]
    assert req["model"] == "claude-opus-5-5" and req["fallbacks"] == "default"
    assert any(t.get("type") == "web_search_20260209" for t in req["tools"])
    assert lead.landlines == ["02155667788"] and lead.mobiles == ["09121234567"]
    assert lead.instagram == "https://instagram.com/kian.gold"
    assert lead.shop_type == "عمده‌فروشی / پخش" and lead.size == "large" and lead.branches == 3
    assert "web" in lead.sources

    # A second run re-uses the cached research without calling Claude.
    client2, messages2 = _client([])
    again = _lead("طلای کیان", 12)
    Enricher(client=client2, cache_file=tmp_path / "enrich.json").enrich([again], limit=5)
    assert messages2.requests == [] and again.mobiles == ["09121234567"]


def test_enricher_nudges_when_model_forgets_the_tool():
    client, messages = _client([
        _block(stop_reason="end_turn", content=[_block(type="text", text="done")]),
        _block(stop_reason="tool_use", content=[_block(type="tool_use", name=SUBMIT_TOOL,
                                                       input={**SUBMIT_INPUT, "found": False})]),
    ])
    lead = _lead("طلای ناشناس", 5)
    Enricher(client=client).enrich([lead])
    assert len(messages.requests) == 2 and lead.enriched and lead.phones == []


def test_enricher_skips_refusals():
    client, _ = _client([_block(stop_reason="refusal", content=[])])
    lead = _lead("طلای الف", 5)
    Enricher(client=client).enrich([lead])
    assert not lead.enriched
