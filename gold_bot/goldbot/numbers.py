"""تبدیل اعداد فارسی/عربی و استخراج قیمت از متن."""
from __future__ import annotations

import re

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
# جداکننده‌های هزارگان رایج: , ، ٬ . فاصله و نیم‌فاصله
_NUMBER_RE = re.compile(r"\d{1,3}(?:[,،٬.\s‌]\d{3})+|\d{4,}")


def normalize_digits(text: str) -> str:
    return text.translate(_DIGITS)


def parse_number(value) -> float | None:
    """'۱۲٬۳۴۵٬۶۷۸' یا '12,345,678' یا 12345678 -> 12345678.0"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = normalize_digits(str(value)).strip()
    match = _NUMBER_RE.search(text)
    if match:
        return float(re.sub(r"\D", "", match.group()))
    try:
        return float(text)
    except ValueError:
        return None


def find_numbers(text: str) -> list[tuple[int, float]]:
    """همه اعداد بزرگ متن را با موقعیتشان برمی‌گرداند."""
    text = normalize_digits(text)
    return [(m.start(), float(re.sub(r"\D", "", m.group()))) for m in _NUMBER_RE.finditer(text)]


def price_near_keyword(text: str, keywords: list[str], lo: float, hi: float,
                       window: int = 120) -> float | None:
    """اولین عدد در بازه [lo, hi] که حداکثر `window` کاراکتر بعد از یکی از کلمات کلیدی آمده باشد."""
    text = normalize_digits(text)
    numbers = find_numbers(text)
    best: tuple[int, float] | None = None
    for kw in keywords:
        for m in re.finditer(re.escape(kw), text):
            end = m.end()
            for pos, num in numbers:
                if end <= pos <= end + window and lo <= num <= hi:
                    dist = pos - end
                    if best is None or dist < best[0]:
                        best = (dist, num)
                    break
    return best[1] if best else None


def fa_digits(text: str) -> str:
    return str(text).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def fmt_toman(value: float | None) -> str:
    if value is None:
        return "—"
    return fa_digits(f"{round(value):,}").replace(",", "٬")
