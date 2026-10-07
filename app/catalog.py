"""Static labels and lookup tables shared by the backend and the UI."""

CATEGORIES: dict[str, str] = {
    "technology": "فناوری و دیجیتال",
    "business": "کسب‌وکار و اقتصاد",
    "finance": "مالی و ارز دیجیتال",
    "health": "سلامت و پزشکی",
    "beauty": "زیبایی و آرایشی",
    "education": "آموزش",
    "travel": "گردشگری و سفر",
    "real_estate": "املاک و ساختمان",
    "ecommerce": "فروشگاهی و خرید",
    "food": "غذا و آشپزی",
    "automotive": "خودرو",
    "sports": "ورزش",
    "home": "خانه و دکوراسیون",
    "lifestyle": "سبک زندگی",
    "general": "عمومی",
}

# Categories whose audiences overlap enough that a link is still topically useful.
RELATED: dict[str, set[str]] = {
    "technology": {"business", "education", "ecommerce", "finance"},
    "business": {"finance", "technology", "ecommerce", "real_estate"},
    "finance": {"business", "technology", "real_estate"},
    "health": {"beauty", "sports", "food", "lifestyle"},
    "beauty": {"health", "lifestyle", "ecommerce"},
    "education": {"technology", "business", "lifestyle"},
    "travel": {"lifestyle", "food"},
    "real_estate": {"home", "business", "finance"},
    "ecommerce": {"technology", "business", "beauty", "home"},
    "food": {"health", "lifestyle", "travel"},
    "automotive": {"technology", "business", "lifestyle"},
    "sports": {"health", "lifestyle"},
    "home": {"real_estate", "lifestyle", "ecommerce"},
    "lifestyle": {"health", "beauty", "travel", "food", "home"},
    "general": set(),
}

PUBLISHER_TYPES: dict[str, str] = {
    "news_agency": "خبرگزاری",
    "news": "سایت خبری",
    "niche": "مجله تخصصی",
    "blog": "وبلاگ",
    "directory": "دایرکتوری / نیازمندی",
}

PRODUCTS: dict[str, str] = {
    "reportage": "رپورتاژ آگهی",
    "news_reportage": "رپورتاژ خبری",
    "guest_post": "پست مهمان",
    "backlink": "بک‌لینک (سایدبار/فوتر)",
    "directory_listing": "ثبت آگهی/پروفایل",
}

LINK_TYPES: dict[str, str] = {
    "dofollow": "فالو",
    "nofollow": "نوفالو",
    "sponsored": "sponsored",
}

GOALS: dict[str, str] = {
    "ranking": "بهبود رتبه کلمات کلیدی",
    "branding": "برندینگ و اعتبار",
    "traffic": "ترافیک ارجاعی",
    "local": "سئو محلی",
}

RISKS: dict[str, str] = {
    "conservative": "محافظه‌کار",
    "balanced": "متعادل",
    "aggressive": "تهاجمی",
}

ANCHOR_TYPES: dict[str, str] = {
    "brand": "برند",
    "naked": "آدرس سایت",
    "generic": "عمومی",
    "partial": "ترکیبی",
    "exact": "دقیق",
}

JALALI_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]
