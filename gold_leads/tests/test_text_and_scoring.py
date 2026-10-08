from leadgen.models import Lead
from leadgen.scoring import score_lead, tier_for
from leadgen.text import (
    extract_phones,
    is_gold_related,
    name_key,
    normalize,
    normalize_instagram,
    normalize_phone,
)


def test_normalize_phone_variants():
    assert normalize_phone("۰۲۱-۵۵۶۶۷۷۸۸") == "02155667788"
    assert normalize_phone("+98 21 5566 7788") == "02155667788"
    assert normalize_phone("0098 912 123 4567") == "09121234567"
    assert normalize_phone("55667788") == "02155667788"  # Tehran number without area code
    assert normalize_phone("9121234567") == "09121234567"
    assert normalize_phone("021 556") is None
    assert normalize_phone("") is None


def test_extract_phones_from_mixed_text():
    text = "تلفن: ۰۲۱-۳۳۱۱۲۲۳۳ و ۳۳۱۱۲۲۳۴ ، موبایل ۰۹۱۲ ۱۲۳ ۴۵۶۷ / +98 21 33112233"
    assert extract_phones(text) == ["02133112233", "02133112234", "09121234567"]


def test_normalize_unifies_arabic_letters_and_digits():
    assert normalize("طلاي كيان ۱۲") == "طلای کیان 12"
    assert normalize("سعادت‌آباد") == "سعادت آباد"


def test_name_key_ignores_generic_words():
    assert name_key("طلا و جواهر کیان") == name_key("گالری طلای كيان") == "کیان"
    assert name_key("طلافروشی") == "طلافروشی"  # nothing left -> keep the words


def test_gold_related():
    assert is_gold_related("گالری طلای ماهان")
    assert is_gold_related("جواهری سعیدی")
    assert is_gold_related("Arya Gold")
    assert not is_gold_related("نانوایی بربری")


def test_instagram_normalization():
    assert normalize_instagram("@kian.gold") == "https://instagram.com/kian.gold"
    assert normalize_instagram("https://www.instagram.com/kian_gold/?hl=fa") == "https://instagram.com/kian_gold"
    assert normalize_instagram("https://instagram.com/p/abc123") == ""
    assert normalize_instagram("") == ""


def test_scoring_prefers_reachable_and_big_shops():
    rich = Lead(name="a", landlines=["02133112233"], mobiles=["09121234567"], instagram="x",
                reviews=250, rating=4.6, sources=["google", "neshan"], size="large")
    bare = Lead(name="b", sources=["neshan"])
    assert score_lead(rich) > 60 and tier_for(score_lead(rich), rich) == "A"
    assert score_lead(bare) == 0 and tier_for(0, bare) == "C"
    closed = Lead(name="c", landlines=["02133112233"], business_status="CLOSED_PERMANENTLY")
    assert score_lead(closed) == 0 and tier_for(0, closed) == "D"
