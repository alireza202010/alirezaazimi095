from types import SimpleNamespace

from leadgen.models import Lead
from leadgen.sheets import SheetSync
from leadgen.table import ALL_TAB, SYNC_TAB, build_tabs


class FakeSpreadsheet:
    url = "https://docs.google.com/spreadsheets/d/x"

    def __init__(self):
        self.sheets = [SimpleNamespace(title="Sheet1", id=0, row_count=1000, col_count=26)]
        self.batches, self.cleared, self.written = [], None, None

    def worksheets(self):
        return list(self.sheets)

    def values_batch_get(self, ranges):
        return {"valueRanges": [{} for _ in ranges]}

    def batch_update(self, body):
        self.batches.append(body)
        for req in body["requests"]:
            if "addSheet" in req:
                props = req["addSheet"]["properties"]
                self.sheets.append(SimpleNamespace(title=props["title"], id=len(self.sheets), row_count=100, col_count=31))

    def values_batch_clear(self, body):
        self.cleared = body

    def values_batch_update(self, body):
        self.written = body


def test_sheet_sync_creates_tabs_and_writes_raw():
    spreadsheet = FakeSpreadsheet()
    client = SimpleNamespace(open_by_key=lambda key: spreadsheet)
    sync = SheetSync("x", "", client=client)
    assert sync.read_tabs() == {"Sheet1": []}

    tabs = build_tabs([Lead(name="طلای الف", district=6, landlines=["02133112233"])], {}, "2026-10-08")
    assert sync.write_tabs(tabs) == spreadsheet.url

    added = [r["addSheet"]["properties"]["title"] for r in spreadsheet.batches[0]["requests"] if "addSheet" in r]
    assert added == list(tabs)
    assert spreadsheet.written["valueInputOption"] == "RAW"  # keeps the 0 of 021...
    assert f"'{ALL_TAB}'!A1" in [d["range"] for d in spreadsheet.written["data"]]
    fmt = spreadsheet.batches[-1]["requests"]
    hidden = [r for r in fmt if r.get("updateSheetProperties", {}).get("fields") == "hidden"]
    sync_id = next(s.id for s in spreadsheet.sheets if s.title == SYNC_TAB)
    assert [r["updateSheetProperties"]["properties"]["sheetId"] for r in hidden] == [sync_id]
    assert any("setDataValidation" in r for r in fmt)
