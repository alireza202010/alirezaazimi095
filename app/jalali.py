"""Minimal Gregorian -> Jalali (Solar Hijri) conversion for schedule labels."""

from datetime import date

from app.catalog import JALALI_MONTHS


_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa_digits(value: object) -> str:
    return str(value).translate(_FA_DIGITS)


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gy2 = gy - 1600
    gm2 = gm - 1
    gd2 = gd - 1
    g_day_no = 365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
    g_day_no += sum(g_days_in_month[:gm2]) + gd2
    if gm2 > 1 and ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0):
        g_day_no += 1

    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365

    j_days_in_month = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]
    jm = 0
    while jm < 11 and j_day_no >= j_days_in_month[jm]:
        j_day_no -= j_days_in_month[jm]
        jm += 1
    return jy, jm + 1, j_day_no + 1


def month_labels(count: int, today: date | None = None) -> list[str]:
    """Labels for the next `count` Jalali months, starting with the coming month."""
    today = today or date.today()
    jy, jm, _ = gregorian_to_jalali(today.year, today.month, today.day)
    labels = []
    for k in range(1, count + 1):
        m = jm + k
        y = jy + (m - 1) // 12
        labels.append(f"{JALALI_MONTHS[(m - 1) % 12]} {fa_digits(y)}")
    return labels


def current_jalali_year(today: date | None = None) -> int:
    today = today or date.today()
    return gregorian_to_jalali(today.year, today.month, today.day)[0]
