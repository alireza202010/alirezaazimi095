"""Persian text helpers: digit/letter normalization, phone parsing, name keys."""

from __future__ import annotations

import re

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "أ": "ا", "إ": "ا", "ٱ": "ا"})
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

# Words that say "this is a gold shop" but don't identify *which* shop.
_GENERIC_NAME_WORDS = {
    "طلا", "طلای", "طلافروشی", "فروشی", "جواهر", "جواهری", "جواهرات", "گالری", "و", "زرگری",
    "سکه", "فروشگاه", "مزون", "خانه", "مرکز", "پخش", "تولیدی", "شعبه", "ساعت",
}

# A name/category matching this is treated as gold-related.
GOLD_PATTERN = re.compile(r"طلا|جواهر|زرگر|سکه|گالری زر|\bزر\b|gold|jewel", re.IGNORECASE)


def to_latin_digits(text: str) -> str:
    return text.translate(_DIGITS)


def to_persian_digits(text: str | int) -> str:
    return str(text).translate(_FA_DIGITS)


def normalize(text: str | None) -> str:
    """Unify Arabic/Persian letters and digits, drop ZWNJ/diacritics, collapse spaces."""
    if not text:
        return ""
    text = to_latin_digits(text).translate(_LETTERS)
    text = re.sub(r"[ً-ْٰ]", "", text)  # harakat
    text = text.replace("‌", " ").replace("‏", "").replace("‎", "")
    return re.sub(r"\s+", " ", text).strip()


def name_key(name: str | None) -> str:
    """Comparison key for a shop name, ignoring generic words like «طلا و جواهر»."""
    words = re.sub(r"[^\w\s]", " ", normalize(name).lower()).split()
    core = [w for w in words if w not in _GENERIC_NAME_WORDS]
    return " ".join(core or words)


def is_gold_related(*texts: str | None) -> bool:
    return any(t and GOLD_PATTERN.search(normalize(t)) for t in texts)


def normalize_phone(raw: str | None) -> str | None:
    """Return a dialable Iranian number (``021xxxxxxxx`` / ``09xxxxxxxxx``) or None."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", to_latin_digits(raw))
    if digits.startswith("0098"):
        digits = digits[4:]
    elif digits.startswith("98") and len(digits) >= 11:
        digits = digits[2:]
    if len(digits) == 8 and digits[0] != "0":  # Tehran number without area code
        digits = "021" + digits
    elif len(digits) == 10 and digits[0] != "0":  # +98 form without the leading zero
        digits = "0" + digits
    if len(digits) == 11 and digits.startswith("0") and digits[1] != "0":
        return digits
    return None


def is_mobile(phone: str) -> bool:
    return phone.startswith("09")


_PHONE_CANDIDATE = re.compile(r"(?:\+|00)?[\d۰-۹٠-٩][\d۰-۹٠-٩\s\-()]{6,16}[\d۰-۹٠-٩]")


def extract_phones(text: str | None) -> list[str]:
    """Find all phone numbers in free text (handles Persian digits and separators)."""
    found: list[str] = []
    for part in re.split(r"[,،;؛/|]", text or ""):
        for match in _PHONE_CANDIDATE.findall(part):
            phone = normalize_phone(match)
            if phone and phone not in found:
                found.append(phone)
    return found


def split_phones(phones: list[str]) -> tuple[list[str], list[str]]:
    """Split normalized numbers into (landlines, mobiles)."""
    landlines = [p for p in phones if not is_mobile(p)]
    mobiles = [p for p in phones if is_mobile(p)]
    return landlines, mobiles


def normalize_instagram(value: str | None) -> str:
    """``@name`` / ``instagram.com/name/`` -> ``https://instagram.com/name``."""
    if not value:
        return ""
    value = value.strip()
    match = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", value)
    handle = match.group(1) if match else value.lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_.]{1,30}", handle) or handle in {"p", "reel", "explore"}:
        return ""
    return f"https://instagram.com/{handle}"
