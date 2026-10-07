"""Labels shared by the backend and the UI."""

INTERESTS: dict[str, str] = {
    "nature": "طبیعت‌گردی",
    "beach": "ساحل و دریا",
    "history": "تاریخ و فرهنگ",
    "shopping": "خرید",
    "food": "غذا و آشپزی محلی",
    "adventure": "ماجراجویی",
    "relaxation": "آرامش و استراحت",
    "entertainment": "تفریحات شهری و سرگرمی",
    "pilgrimage": "زیارت",
    "ski": "اسکی و ورزش‌های زمستانی",
    "desert": "کویرگردی",
}

TRAVELER_TYPES: dict[str, str] = {
    "family": "خانواده با کودک",
    "couple": "زوج",
    "friends": "دوستان",
    "solo": "تنها",
}

SCOPES: dict[str, str] = {
    "both": "داخلی و خارجی",
    "domestic": "فقط داخلی",
    "international": "فقط خارجی",
}

COMFORT_LEVELS: dict[str, str] = {
    "economy": "اقتصادی",
    "standard": "استاندارد",
    "luxury": "لوکس",
}

VISA_TYPES: dict[str, str] = {
    "domestic": "سفر داخلی",
    "free": "بدون نیاز به ویزا",
    "on_arrival": "ویزای فرودگاهی",
    "required": "نیاز به ویزا (الکترونیکی یا از طریق آژانس)",
    "embassy": "ویزای سفارت (زمان‌بر)",
}

TRANSPORT_MODES: dict[str, str] = {
    "flight": "پرواز",
    "train": "قطار یا اتوبوس",
    "road": "خودرو یا اتوبوس",
}

JALALI_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]
