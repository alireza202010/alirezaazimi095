"""تنظیمات از متغیرهای محیطی و فایل platforms.json."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PLATFORMS_FILE = Path(__file__).resolve().parent.parent / "platforms.json"


@dataclass
class Platform:
    key: str
    name: str
    url: str
    method: str = "browser"           # json | html | browser
    enabled: bool = True
    verified: bool = False            # آیا آدرس/الگو روی سایت واقعی تست شده؟
    unit: str = "toman"               # toman | rial  (قیمت هر گرم طلای ۱۸ عیار)
    api_url: str | None = None        # برای json
    capture_url_contains: str | None = None  # برای browser: پاسخ XHR حاوی این رشته
    buy_path: str | None = None       # مسیر JSON قیمت خرید کاربر (مثل data.buy)
    sell_path: str | None = None      # مسیر JSON قیمت فروش کاربر
    buy_regex: str | None = None      # برای html: گروه اول = قیمت
    sell_regex: str | None = None
    buy_keywords: list[str] = field(default_factory=lambda: ["قیمت خرید", "خرید"])
    sell_keywords: list[str] = field(default_factory=lambda: ["قیمت فروش", "فروش"])
    headers: dict[str, str] = field(default_factory=dict)
    wait_ms: int = 4000


@dataclass
class Settings:
    bot_token: str = ""
    channel_id: str = ""
    interval_minutes: int = 10
    telegram_api_base: str = "https://api.telegram.org"
    proxy: str | None = None          # پروکسی برای درخواست‌های تلگرام
    scrape_proxy: str | None = None   # پروکسی برای سایت‌های طلا (معمولاً خالی؛ سرور ایران)
    edit_last_message: bool = False   # True: یک پیام ثابت را ویرایش کن به‌جای پست جدید
    only_on_change: bool = True       # اگر هیچ قیمتی عوض نشده، پست نکن
    quiet_hours: tuple[int, int] | None = None  # مثلاً (0, 8) یعنی ۰ تا ۸ صبح پست نکن
    min_price: float = 1_000_000      # بازه معقول قیمت هر گرم ۱۸ عیار به تومان
    max_price: float = 200_000_000
    db_path: str = "data/goldbot.sqlite3"
    channel_title: str = "قیمت لحظه‌ای طلای آنلاین"
    channel_handle: str = ""
    timeout: float = 20.0

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get
        quiet = env("QUIET_HOURS")  # "0-8"
        quiet_hours = None
        if quiet:
            a, b = quiet.split("-")
            quiet_hours = (int(a), int(b))
        return cls(
            bot_token=env("BOT_TOKEN", ""),
            channel_id=env("CHANNEL_ID", ""),
            interval_minutes=int(env("INTERVAL_MINUTES", "10")),
            telegram_api_base=env("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/"),
            proxy=env("TELEGRAM_PROXY") or None,
            scrape_proxy=env("SCRAPE_PROXY") or None,
            edit_last_message=env("EDIT_LAST_MESSAGE", "0") == "1",
            only_on_change=env("ONLY_ON_CHANGE", "1") == "1",
            quiet_hours=quiet_hours,
            min_price=float(env("MIN_PRICE", "1000000")),
            max_price=float(env("MAX_PRICE", "200000000")),
            db_path=env("DB_PATH", "data/goldbot.sqlite3"),
            channel_title=env("CHANNEL_TITLE", "قیمت لحظه‌ای طلای آنلاین"),
            channel_handle=env("CHANNEL_HANDLE", ""),
            timeout=float(env("HTTP_TIMEOUT", "20")),
        )


def load_platforms(path: str | os.PathLike | None = None) -> list[Platform]:
    path = Path(path or os.environ.get("PLATFORMS_FILE") or DEFAULT_PLATFORMS_FILE)
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Platform(**item) for item in raw["platforms"]]
