"""دریافت قیمت از هر پلتفرم: json (API مستقیم)، html (الگوی متنی) یا browser (رندر با Playwright)."""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass

import httpx

from .config import Platform, Settings
from .numbers import normalize_digits, parse_number, price_near_keyword

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)


@dataclass
class Quote:
    key: str
    name: str
    buy: float | None = None   # قیمتی که کاربر می‌خرد (تومان/گرم)
    sell: float | None = None  # قیمتی که کاربر می‌فروشد (تومان/گرم)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and (self.buy is not None or self.sell is not None)

    @property
    def spread(self) -> float | None:
        if self.buy and self.sell:
            return (self.buy - self.sell) / self.buy * 100
        return None


def json_path(data, path: str | None):
    """'data.prices.0.buy' -> مقدار. کلیدهای عددی برای لیست‌ها ایندکس هستند."""
    if not path:
        return None
    cur = data
    for part in path.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            if part not in cur:
                return None
            cur = cur[part]
        else:
            return None
    return cur


def _to_toman(value, platform: Platform) -> float | None:
    num = parse_number(value)
    if num is None:
        return None
    return num / 10 if platform.unit == "rial" else num


def _sane(value: float | None, settings: Settings) -> float | None:
    if value is None:
        return None
    return value if settings.min_price <= value <= settings.max_price else None


def extract_from_json(data, platform: Platform, settings: Settings) -> tuple[float | None, float | None]:
    buy = _sane(_to_toman(json_path(data, platform.buy_path), platform), settings)
    sell = _sane(_to_toman(json_path(data, platform.sell_path), platform), settings)
    return buy, sell


def extract_from_text(text: str, platform: Platform, settings: Settings) -> tuple[float | None, float | None]:
    """اول regex اختصاصی؛ اگر نبود، عدد نزدیک به کلمات «خرید/فروش»."""
    text = normalize_digits(text)
    lo, hi = settings.min_price, settings.max_price
    if platform.unit == "rial":
        lo, hi = lo * 10, hi * 10

    def by_regex(pattern):
        if not pattern:
            return None
        m = re.search(pattern, text, re.S)
        return m.group(1) if m else None

    buy_raw = by_regex(platform.buy_regex) or price_near_keyword(text, platform.buy_keywords, lo, hi)
    sell_raw = by_regex(platform.sell_regex) or price_near_keyword(text, platform.sell_keywords, lo, hi)
    buy = _sane(_to_toman(buy_raw, platform), settings)
    sell = _sane(_to_toman(sell_raw, platform), settings)
    # «فروش» و «خرید» در بعضی سایت‌ها نزدیک هم‌اند؛ قیمت خرید کاربر نباید کمتر از فروش باشد
    if buy and sell and buy < sell:
        buy, sell = sell, buy
    return buy, sell


async def _fetch_http(platform: Platform, settings: Settings, client: httpx.AsyncClient) -> Quote:
    url = platform.api_url if platform.method == "json" else platform.url
    resp = await client.get(url, headers={"User-Agent": USER_AGENT, **platform.headers})
    resp.raise_for_status()
    if platform.method == "json":
        buy, sell = extract_from_json(resp.json(), platform, settings)
    else:
        buy, sell = extract_from_text(resp.text, platform, settings)
    return Quote(platform.key, platform.name, buy, sell)


async def _fetch_browser(platform: Platform, settings: Settings, browser) -> Quote:
    """صفحه را رندر می‌کند. اگر capture_url_contains تنظیم شده باشد، JSON آن درخواست را می‌خواند؛
    وگرنه از متن نهایی صفحه با کلمات کلیدی استخراج می‌کند."""
    context = await browser.new_context(user_agent=USER_AGENT, locale="fa-IR")
    page = await context.new_page()
    captured: list = []

    async def on_response(response):
        if platform.capture_url_contains and platform.capture_url_contains in response.url:
            try:
                captured.append(await response.json())
            except Exception:  # noqa: BLE001 - پاسخ غیر JSON
                pass

    page.on("response", on_response)
    try:
        await page.goto(platform.url, wait_until="domcontentloaded", timeout=settings.timeout * 1000)
        await page.wait_for_timeout(platform.wait_ms)
        buy = sell = None
        for data in reversed(captured):
            buy, sell = extract_from_json(data, platform, settings)
            if buy or sell:
                break
        if not (buy or sell):
            text = await page.inner_text("body")
            log.debug("%s text: %r", platform.key, text[:300])
            buy, sell = extract_from_text(text, platform, settings)
        return Quote(platform.key, platform.name, buy, sell)
    finally:
        await context.close()


async def fetch_all(platforms: list[Platform], settings: Settings) -> list[Quote]:
    active = [p for p in platforms if p.enabled]
    needs_browser = any(p.method == "browser" for p in active)
    quotes: dict[str, Quote] = {}

    async with httpx.AsyncClient(timeout=settings.timeout, follow_redirects=True,
                                 proxy=settings.scrape_proxy) as client:
        pw = browser = None
        if needs_browser:
            try:
                from playwright.async_api import async_playwright
                pw = await async_playwright().start()
                launch = {"proxy": {"server": settings.scrape_proxy}} if settings.scrape_proxy else {}
                if os.environ.get("CHROMIUM_PATH"):
                    launch["executable_path"] = os.environ["CHROMIUM_PATH"]
                browser = await pw.chromium.launch(**launch)
            except Exception as exc:  # noqa: BLE001
                log.error("Playwright در دسترس نیست: %s", exc)

        sem = asyncio.Semaphore(4)

        async def one(p: Platform):
            async with sem:
                try:
                    if p.method == "browser":
                        if browser is None:
                            raise RuntimeError("مرورگر در دسترس نیست")
                        q = await _fetch_browser(p, settings, browser)
                    else:
                        q = await _fetch_http(p, settings, client)
                    if not q.ok:
                        q.error = "قیمت در صفحه پیدا نشد"
                except Exception as exc:  # noqa: BLE001
                    q = Quote(p.key, p.name, error=f"{type(exc).__name__}: {exc}"[:200])
                if q.error:
                    log.warning("%s: %s", p.name, q.error)
                quotes[p.key] = q

        try:
            await asyncio.gather(*(one(p) for p in active))
        finally:
            if browser:
                await browser.close()
            if pw:
                await pw.stop()

    return [quotes[p.key] for p in active]
