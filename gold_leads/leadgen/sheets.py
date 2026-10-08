"""Google Sheets sync (service account) — a handful of batched API calls per run."""

from __future__ import annotations

import logging

from .table import ALL_TAB, HEADERS, STATUS_COL, STATUS_OPTIONS, SUMMARY_TAB, SYNC_TAB

log = logging.getLogger(__name__)


def _quote(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"


class SheetSync:
    def __init__(self, sheet_id: str, service_account_file: str, client=None):
        if client is None:
            import gspread

            client = gspread.service_account(filename=service_account_file)
        self.spreadsheet = client.open_by_key(sheet_id)

    def read_tabs(self) -> dict[str, list[list]]:
        titles = [ws.title for ws in self.spreadsheet.worksheets()]
        if not titles:
            return {}
        resp = self.spreadsheet.values_batch_get([_quote(t) for t in titles])
        return {title: vr.get("values", []) for title, vr in zip(titles, resp.get("valueRanges", []))}

    def write_tabs(self, tabs: dict[str, list[list]]) -> str:
        existing = {ws.title: ws for ws in self.spreadsheet.worksheets()}
        # 1) create missing tabs / grow existing ones so the data fits
        requests = []
        for title, rows in tabs.items():
            n_rows, n_cols = max(len(rows) + 50, 100), max(len(HEADERS), 10)
            ws = existing.get(title)
            if ws is None:
                requests.append({"addSheet": {"properties": {
                    "title": title, "rightToLeft": True,
                    "gridProperties": {"rowCount": n_rows, "columnCount": n_cols, "frozenRowCount": 1},
                }}})
            elif ws.row_count < n_rows or ws.col_count < n_cols:
                requests.append({"updateSheetProperties": {
                    "properties": {"sheetId": ws.id, "gridProperties": {
                        "rowCount": max(ws.row_count, n_rows), "columnCount": max(ws.col_count, n_cols)}},
                    "fields": "gridProperties.rowCount,gridProperties.columnCount",
                }})
        if requests:
            self.spreadsheet.batch_update({"requests": requests})
        sheet_ids = {ws.title: ws.id for ws in self.spreadsheet.worksheets()}

        # 2) clear old values and write the new ones (RAW keeps leading zeros of phone numbers)
        self.spreadsheet.values_batch_clear(body={"ranges": [_quote(t) for t in tabs]})
        self.spreadsheet.values_batch_update({
            "valueInputOption": "RAW",
            "data": [{"range": f"{_quote(t)}!A1", "values": rows} for t, rows in tabs.items()],
        })

        # 3) formatting: RTL, frozen bold header, filter, status dropdown, column widths
        fmt = []
        status_col = HEADERS.index(STATUS_COL)
        for title, rows in tabs.items():
            sid = sheet_ids[title]
            width = len(rows[0]) if rows else 1
            fmt += [
                {"updateSheetProperties": {
                    "properties": {"sheetId": sid, "rightToLeft": True, "gridProperties": {"frozenRowCount": 1}},
                    "fields": "rightToLeft,gridProperties.frozenRowCount"}},
                {"repeatCell": {
                    "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {"userEnteredFormat": {
                        "textFormat": {"bold": True}, "backgroundColor": {"red": 0.98, "green": 0.9, "blue": 0.6}}},
                    "fields": "userEnteredFormat(textFormat,backgroundColor)"}},
                {"autoResizeDimensions": {"dimensions": {
                    "sheetId": sid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": width}}},
            ]
            if title == SYNC_TAB:
                fmt.append({"updateSheetProperties": {
                    "properties": {"sheetId": sid, "hidden": True}, "fields": "hidden"}})
            if title in (SUMMARY_TAB, SYNC_TAB):
                continue
            fmt.append({"setBasicFilter": {"filter": {"range": {
                "sheetId": sid, "startRowIndex": 0, "endRowIndex": len(rows), "startColumnIndex": 0, "endColumnIndex": width}}}})
            fmt.append({"setDataValidation": {
                "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": max(len(rows), 2),
                          "startColumnIndex": status_col, "endColumnIndex": status_col + 1},
                "rule": {"condition": {"type": "ONE_OF_LIST",
                                       "values": [{"userEnteredValue": v} for v in STATUS_OPTIONS]},
                         "showCustomUi": True, "strict": False}}})
        self.spreadsheet.batch_update({"requests": fmt})
        log.info("Google Sheet updated: %d tabs, %d leads", len(tabs), len(tabs.get(ALL_TAB, [])) - 1)
        return self.spreadsheet.url
