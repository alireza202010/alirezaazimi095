"""Turn leads into spreadsheet tabs, keeping whatever the sales team typed in earlier runs.

Tabs: «خلاصه مناطق» (summary), «همه لیدها» (all leads), one tab per district and a hidden
``_sync`` tab.
The four sales columns (status, owner, last contact, notes) are never overwritten:
on every run they are read back from the existing sheet — from the main tab *and*
the district tabs, whichever copy a person changed since the last sync (if both were
changed, the main tab wins) — and written into the fresh rows.
"""

from __future__ import annotations

from collections import Counter

from .models import UNKNOWN_DISTRICT, Lead, district_label
from .text import name_key

SUMMARY_TAB = "خلاصه مناطق"
ALL_TAB = "همه لیدها"
SYNC_TAB = "_sync"  # hidden: sales values as last written, used to detect edits

ID_COL = "شناسه"
STATUS_COL = "وضعیت"
FIRST_SEEN_COL = "اولین مشاهده"
SALES_COLS = [STATUS_COL, "مسئول فروش", "تاریخ آخرین تماس", "یادداشت فروش"]
STATUS_OPTIONS = ["جدید", "تماس گرفته شد", "پاسخ نداد", "علاقه‌مند", "جلسه/دمو", "مشتری شد", "رد کرد", "شماره اشتباه"]

SIZE_FA = {"small": "کوچک", "medium": "متوسط", "large": "بزرگ"}
DISTRICT_SOURCE_FA = {
    "neshan": "دقیق (نشان)",
    "polygon": "دقیق (مرز مناطق)",
    "address": "از متن آدرس",
    "neighbourhood": "تقریبی (نام محله)",
    "": "",
}

HEADERS = [
    ID_COL, "منطقه", "کد منطقه", "محله", "نام فروشگاه", "تلفن ثابت", "موبایل", "اینستاگرام", "وبسایت",
    "آدرس", "رتبه لید", "امتیاز لید", "نوع کسب‌وکار", "اندازه", "تعداد شعب", "امتیاز گوگل", "تعداد نظرات",
    "لینک گوگل مپ", "لینک نشان", "یادداشت AI برای فروش", "ساعات کاری",
    *SALES_COLS,
    "منابع داده", "دقت منطقه", "عرض جغرافیایی", "طول جغرافیایی", FIRST_SEEN_COL, "آخرین بروزرسانی",
]


def lead_values(lead: Lead) -> dict:
    return {
        ID_COL: lead.lead_id,
        "منطقه": lead.district_label,
        "کد منطقه": lead.district or "",
        "محله": lead.neighbourhood,
        "نام فروشگاه": lead.name,
        "تلفن ثابت": " / ".join(lead.landlines),
        "موبایل": " / ".join(lead.mobiles),
        "اینستاگرام": lead.instagram,
        "وبسایت": lead.website,
        "آدرس": lead.address,
        "رتبه لید": lead.tier,
        "امتیاز لید": lead.score,
        "نوع کسب‌وکار": lead.shop_type,
        "اندازه": SIZE_FA.get(lead.size, ""),
        "تعداد شعب": lead.branches or "",
        "امتیاز گوگل": lead.rating if lead.rating is not None else "",
        "تعداد نظرات": lead.reviews if lead.reviews is not None else "",
        "لینک گوگل مپ": lead.maps_url,
        "لینک نشان": lead.neshan_url,
        "یادداشت AI برای فروش": lead.ai_note,
        "ساعات کاری": lead.opening_hours,
        "منابع داده": ", ".join(lead.sources),
        "دقت منطقه": DISTRICT_SOURCE_FA.get(lead.district_source, lead.district_source),
        "عرض جغرافیایی": round(lead.lat, 6) if lead.lat is not None else "",
        "طول جغرافیایی": round(lead.lng, 6) if lead.lng is not None else "",
    }


def rows_to_dicts(rows: list[list]) -> list[dict]:
    if not rows:
        return []
    header = [str(h) for h in rows[0]]
    return [dict(zip(header, [*row, *[""] * (len(header) - len(row))])) for row in rows[1:] if any(row)]


def _sales_of(row: dict) -> dict:
    return {col: row.get(col, "") for col in [*SALES_COLS, FIRST_SEEN_COL]}


def collect_existing(tabs: dict[str, list[list]]) -> dict[str, dict]:
    """{lead id: full existing row dict} with district-tab sales edits folded in.

    The hidden ``_sync`` tab holds the sales values as last written by the agent, so
    for every cell we can tell which copy (main tab or a district tab) a person changed.
    """
    main = {r[ID_COL]: r for r in rows_to_dicts(tabs.get(ALL_TAB, [])) if r.get(ID_COL)}
    baseline = {r[ID_COL]: r for r in rows_to_dicts(tabs.get(SYNC_TAB, [])) if r.get(ID_COL)}
    for title, rows in tabs.items():
        if title in (ALL_TAB, SUMMARY_TAB, SYNC_TAB):
            continue
        for row in rows_to_dicts(rows):
            lid = row.get(ID_COL)
            if lid not in main:
                continue
            base = baseline.get(lid)
            for col in SALES_COLS:
                value, current = str(row.get(col, "")), str(main[lid].get(col, ""))
                if value == current:
                    continue
                if base is not None:
                    edited_here = value != str(base.get(col, ""))
                    edited_main = current != str(base.get(col, ""))
                    if edited_here and not edited_main:
                        main[lid][col] = value
                elif value and not current:  # no baseline (older sheet): fill blanks only
                    main[lid][col] = value
    return main


def _row_phones(row: dict) -> set[str]:
    text = f"{row.get('تلفن ثابت', '')} / {row.get('موبایل', '')}"
    return {p.strip() for p in text.split("/") if p.strip()}


def build_tabs(leads: list[Lead], existing_tabs: dict[str, list[list]], today: str) -> dict[str, list[list]]:
    existing = collect_existing(existing_tabs)
    by_phone: dict[str, str] = {}
    by_name: dict[tuple[str, str], str] = {}
    for lid, row in existing.items():
        for phone in _row_phones(row):
            by_phone.setdefault(phone, lid)
        by_name.setdefault((name_key(row.get("نام فروشگاه", "")), str(row.get("منطقه", ""))), lid)

    used: set[str] = set()
    records: list[dict] = []
    for lead in leads:
        values = lead_values(lead)
        old_id = lead.lead_id if lead.lead_id in existing else None
        if old_id is None:  # same shop may have got a different id (e.g. Google found it this time)
            old_id = next((by_phone[p] for p in lead.phones if p in by_phone), None) or by_name.get(
                (name_key(lead.name), lead.district_label)
            )
            if old_id in used:
                old_id = None
        sales = _sales_of(existing[old_id]) if old_id else {}
        if old_id:
            used.add(old_id)
        values.update({col: sales.get(col, "") for col in SALES_COLS})
        values[STATUS_COL] = values[STATUS_COL] or STATUS_OPTIONS[0]
        values[FIRST_SEEN_COL] = sales.get(FIRST_SEEN_COL) or today
        values["آخرین بروزرسانی"] = today
        records.append(values)
    # Rows not found this run (or added by hand) are kept, never silently deleted.
    records.extend(row for lid, row in existing.items() if lid not in used)

    def sort_key(r: dict):
        code = r.get("کد منطقه")
        code = int(code) if str(code).isdigit() else 99
        score = r.get("امتیاز لید")
        score = int(score) if str(score).lstrip("-").isdigit() else 0
        return code, -score, str(r.get("نام فروشگاه", ""))

    records.sort(key=sort_key)
    to_row = lambda r: [r.get(h, "") for h in HEADERS]  # noqa: E731

    tabs: dict[str, list[list]] = {SUMMARY_TAB: summary_rows(records), ALL_TAB: [HEADERS, *map(to_row, records)]}
    for district in [*range(1, 23), None]:
        label = district_label(district)
        rows = [to_row(r) for r in records if r.get("منطقه", UNKNOWN_DISTRICT) == label]
        if rows:
            tabs[label] = [HEADERS, *rows]
    tabs[SYNC_TAB] = [[ID_COL, *SALES_COLS], *([r.get(ID_COL, ""), *(r.get(c, "") for c in SALES_COLS)] for r in records)]
    return tabs


def summary_rows(records: list[dict]) -> list[list]:
    header = ["منطقه", "تعداد لید", "دارای تلفن ثابت", "دارای موبایل", "دارای اینستاگرام",
              "رتبه A", "رتبه B", "رتبه C", "پیگیری شده"]
    stats: dict[str, Counter] = {}
    for r in records:
        c = stats.setdefault(r.get("منطقه") or UNKNOWN_DISTRICT, Counter())
        c["total"] += 1
        c["landline"] += bool(r.get("تلفن ثابت"))
        c["mobile"] += bool(r.get("موبایل"))
        c["instagram"] += bool(r.get("اینستاگرام"))
        c[f"tier_{r.get('رتبه لید')}"] += 1
        c["followed"] += r.get(STATUS_COL) not in ("", STATUS_OPTIONS[0], None)
    order = [district_label(d) for d in [*range(1, 23), None]]
    rows = [header]
    total = Counter()
    for label in sorted(stats, key=lambda l: order.index(l) if l in order else len(order)):
        c = stats[label]
        total.update(c)
        rows.append([label, c["total"], c["landline"], c["mobile"], c["instagram"],
                     c["tier_A"], c["tier_B"], c["tier_C"], c["followed"]])
    rows.append(["جمع کل", total["total"], total["landline"], total["mobile"], total["instagram"],
                 total["tier_A"], total["tier_B"], total["tier_C"], total["followed"]])
    return rows

