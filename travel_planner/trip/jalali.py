"""Gregorian <-> Jalali (Solar Hijri) conversion."""

from datetime import date

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_G_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
_J_DAYS = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]


def fa_digits(value: object) -> str:
    return str(value).translate(_FA_DIGITS)


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    gy2 = gy - 1600
    g_day_no = 365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
    g_day_no += sum(_G_DAYS[: gm - 1]) + gd - 1
    if gm > 2 and ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0):
        g_day_no += 1
    j_day_no = g_day_no - 79
    j_np, j_day_no = divmod(j_day_no, 12053)
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365
    jm = 0
    while jm < 11 and j_day_no >= _J_DAYS[jm]:
        j_day_no -= _J_DAYS[jm]
        jm += 1
    return jy, jm + 1, j_day_no + 1


def to_jalali(d: date) -> tuple[int, int, int]:
    return gregorian_to_jalali(d.year, d.month, d.day)


def is_nowruz(d: date) -> bool:
    """Nowruz holidays: 1-13 Farvardin, the peak domestic and outbound travel season."""
    _, jm, jd = to_jalali(d)
    return jm == 1 and jd <= 13
