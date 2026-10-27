from goldbot.config import Platform, Settings, load_platforms
from goldbot.numbers import fmt_toman, parse_number, price_near_keyword
from goldbot.scrapers import extract_from_json, extract_from_text, json_path

S = Settings()


def test_parse_persian_number():
    assert parse_number("۱۲٬۳۴۵٬۶۷۸ تومان") == 12345678
    assert parse_number("12,345,678") == 12345678
    assert parse_number(9876543) == 9876543
    assert parse_number("بدون عدد") is None


def test_fmt_toman():
    assert fmt_toman(12345678.4) == "۱۲٬۳۴۵٬۶۷۸"
    assert fmt_toman(None) == "—"


def test_price_near_keyword_skips_out_of_range():
    text = "قیمت خرید: ۱۸ عیار  ۷٬۲۵۰٬۰۰۰ تومان | قیمت فروش ۷٬۱۰۰٬۰۰۰"
    assert price_near_keyword(text, ["قیمت خرید"], 1e6, 2e8) == 7250000
    assert price_near_keyword(text, ["قیمت فروش"], 1e6, 2e8) == 7100000


def test_json_path():
    data = {"data": {"prices": [{"buy": "1"}, {"buy": 72500000}]}}
    assert json_path(data, "data.prices.1.buy") == 72500000
    assert json_path(data, "data.missing") is None
    assert json_path(data, "data.prices.9.buy") is None


def test_extract_json_rial_to_toman():
    p = Platform("x", "X", "u", method="json", unit="rial", buy_path="d.b", sell_path="d.s")
    assert extract_from_json({"d": {"b": 72_500_000, "s": "71,000,000"}}, p, S) == (7_250_000, 7_100_000)


def test_extract_json_rejects_insane_values():
    p = Platform("x", "X", "u", method="json", buy_path="b", sell_path="s")
    assert extract_from_json({"b": 12, "s": 10**12}, p, S) == (None, None)


def test_extract_text_with_regex_and_swap():
    p = Platform("x", "X", "u", method="html", buy_regex=r'data-buy="([\d,]+)"',
                 sell_regex=r'data-sell="([\d,]+)"')
    html = '<div data-buy="7,100,000" data-sell="7,250,000"></div>'
    assert extract_from_text(html, p, S) == (7_250_000, 7_100_000)


def test_extract_text_keywords():
    p = Platform("x", "X", "u", method="html")
    text = "طلای ۱۸ عیار\nقیمت خرید\n۷٬۲۵۰٬۰۰۰ تومان\nقیمت فروش\n۷٬۱۵۰٬۰۰۰ تومان"
    assert extract_from_text(text, p, S) == (7_250_000, 7_150_000)


def test_platforms_file_loads():
    platforms = load_platforms()
    assert len(platforms) == 11
    assert len({p.key for p in platforms}) == 11
