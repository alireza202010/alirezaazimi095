"""Turn leads into spreadsheet tabs, keeping whatever the sales team typed in earlier runs.

Tabs: «خلاصه مناطق» (summary), «کاندیدهای نمایندگی» (best representative candidates per
district), «همه لیدها» (all leads), one tab per district and a hidden ``_sync`` tab.
The four sales columns (status, owner, last contact, notes) are never overwritten:
on every run they are read back from the existing sheet — from the main tab *and*
the other tabs, whichever copy a person changed since the last sync (if both were
changed, the main tab wins) — and written into the fresh rows.
"""

from __future__ import annotations

from collections import Counter

from .models import UNKNOWN_DISTRICT, Lead, district_label
from .text import has_bullion_hint, name_key

SUMMARY_TAB = "خلاصه مناطق"
CANDIDATES_TAB = "کاندیدهای نمایندگی"
ALL_TAB = "همه لیدها"
CANDIDATES_PER_DISTRICT = 3
SYNC_TAB = "_sync"  # hidden: sales values as last written, used to detect edits

ID_COL = "شناسه"
STATUS_COL = "وضعیت"
FIRST_SEEN_COL = "اولین مشاهده"
SALES_COLS = [STATUS_COL, "مسئول فروش", "تاریخ آخرین تماس", "یادداشت فروش"]
STATUS_OPTIONS = [
    "جدید", "پیام ارسال شد", "تماس گرفته شد", "پاسخ نداد", "علاقه‌مند به نمایندگی", "ارسال شرایط نمایندگی",
    "جلسه حضوری", "قرارداد نمایندگی", "رد کرد", "شماره اشتباه",
]
SIGNED_STATUS = "قرارداد نمایندگی"
CLOSED_STATUSES = {"رد کرد", "شماره اشتباه", SIGNED_STATUS}

SIZE_FA = {"small": "کوچک", "medium": "متوسط", "large": "بزرگ"}
YES_NO_FA = {"yes": "بله", "no": "خیر"}
FIT_FA = {"high": "بالا", "medium": "متوسط", "low": "پایین"}
RANK_COL = "رتبه در منطقه"
DISTRICT_SOURCE_FA = {
    "neshan": "دقیق (نشان)",
    "polygon": "دقیق (مرز مناطق)",
    "address": "از متن آدرس",
    "neighbourhood": "تقریبی (نام محله)",
    "": "",
}

HEADERS = [
    ID_COL, "منطقه", "کد منطقه", "محله", "نام فروشگاه", "تلفن ثابت", "موبایل", "اینستاگرام", "وبسایت",
    "آدرس", "رتبه لید", "امتیاز لید", RANK_COL, "تناسب برای نمایندگی", "دلیل تناسب",
    "فروش شمش/آبشده/سکه", "برندهای شمش/سکه فعلی", "عمده‌فروش/پخش", "نوع کسب‌وکار", "اندازه", "تعداد شعب",
    "فالوور اینستاگرام", "امتیاز گوگل", "تعداد نظرات", "یادداشت AI برای فروش", "پیام پیشنهادی اول",
    "لینک گوگل مپ", "لینک نشان", "ساعات کاری",
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
        "تناسب برای نمایندگی": FIT_FA.get(lead.agency_fit, ""),
        "دلیل تناسب": lead.fit_reason,
        "فروش شمش/آبشده/سکه": YES_NO_FA.get(lead.sells_bullion)
        or ("احتمالاً (از نام)" if has_bullion_hint(lead.name, lead.category) else ""),
        "برندهای شمش/سکه فعلی": "، ".join(lead.bullion_brands),
        "عمده‌فروش/پخش": YES_NO_FA.get(lead.wholesale, ""),
        "فالوور اینستاگرام": lead.instagram_followers or "",
        "پیام پیشنهادی اول": lead.outreach_message,
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
        if title in (ALL_TAB, SUMMARY_TAB, SYNC_TAB):  # district tabs and the candidates tab
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
    rank: Counter = Counter()
    for r in records:  # records are sorted by district, then score
        if str(r.get("کد منطقه")).isdigit():
            rank[r["کد منطقه"]] += 1
            r[RANK_COL] = rank[r["کد منطقه"]]
        else:
            r[RANK_COL] = ""
    to_row = lambda r: [r.get(h, "") for h in HEADERS]  # noqa: E731

    tabs: dict[str, list[list]] = {
        SUMMARY_TAB: summary_rows(records),
        CANDIDATES_TAB: candidate_rows(records),
        ALL_TAB: [HEADERS, *map(to_row, records)],
    }
    for district in [*range(1, 23), None]:
        label = district_label(district)
        rows = [to_row(r) for r in records if r.get("منطقه", UNKNOWN_DISTRICT) == label]
        if rows:
            tabs[label] = [HEADERS, *rows]
    tabs[SYNC_TAB] = [[ID_COL, *SALES_COLS], *([r.get(ID_COL, ""), *(r.get(c, "") for c in SALES_COLS)] for r in records)]
    return tabs


CANDIDATE_HEADERS = [
    "منطقه", "نام فروشگاه", "امتیاز لید", "تناسب برای نمایندگی", "فروش شمش/آبشده/سکه", "برندهای شمش/سکه فعلی",
    "تلفن ثابت", "موبایل", "اینستاگرام", "دلیل تناسب", "پیام پیشنهادی اول", *SALES_COLS, "آدرس", ID_COL,
]


def candidate_rows(records: list[dict]) -> list[list]:
    """Top shops per district that are still open for an agency deal (not rejected / signed / closed)."""
    picked: Counter = Counter()
    rows = [CANDIDATE_HEADERS]
    for r in records:  # already sorted by district and score
        code = r.get("کد منطقه")
        if not str(code).isdigit() or r.get("رتبه لید") == "D" or r.get(STATUS_COL) in CLOSED_STATUSES:
            continue
        if picked[code] >= CANDIDATES_PER_DISTRICT:
            continue
        picked[code] += 1
        rows.append([r.get(h, "") for h in CANDIDATE_HEADERS])
    return rows


def summary_rows(records: list[dict]) -> list[list]:
    header = ["منطقه", "تعداد لید", "دارای تلفن ثابت", "دارای موبایل", "دارای اینستاگرام",
              "فروشنده شمش/آبشده/سکه", "تناسب بالا", "رتبه A", "رتبه B", "رتبه C", "پیگیری شده", "قرارداد نمایندگی"]
    stats: dict[str, Counter] = {}
    for r in records:
        c = stats.setdefault(r.get("منطقه") or UNKNOWN_DISTRICT, Counter())
        c["total"] += 1
        c["landline"] += bool(r.get("تلفن ثابت"))
        c["mobile"] += bool(r.get("موبایل"))
        c["instagram"] += bool(r.get("اینستاگرام"))
        c["bullion"] += str(r.get("فروش شمش/آبشده/سکه", "")) == "بله"
        c["fit_high"] += r.get("تناسب برای نمایندگی") == "بالا"
        c["signed"] += r.get(STATUS_COL) == SIGNED_STATUS
        c[f"tier_{r.get('رتبه لید')}"] += 1
        c["followed"] += r.get(STATUS_COL) not in ("", STATUS_OPTIONS[0], None)
    order = [district_label(d) for d in [*range(1, 23), None]]
    rows = [header]
    total = Counter()
    for label in sorted(stats, key=lambda l: order.index(l) if l in order else len(order)):
        c = stats[label]
        total.update(c)
        rows.append([label, *_summary_cells(c)])
    rows.append(["جمع کل", *_summary_cells(total)])
    return rows


def _summary_cells(c: Counter) -> list[int]:
    keys = ["total", "landline", "mobile", "instagram", "bullion", "fit_high", "tier_A", "tier_B", "tier_C",
            "followed", "signed"]
    return [c[k] for k in keys]
