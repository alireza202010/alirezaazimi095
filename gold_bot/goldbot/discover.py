"""ابزار کشف API قیمت یک سایت.

  python -m goldbot.discover https://milli.gold

صفحه را با مرورگر باز می‌کند، همه پاسخ‌های JSON را ضبط می‌کند و هر جا عددی در بازه قیمت طلا
پیدا شود، آدرس درخواست و مسیر JSON آن را چاپ می‌کند تا در platforms.json بگذارید
(method=json با api_url و buy_path/sell_path، یا method=browser با capture_url_contains).
"""
from __future__ import annotations

import asyncio
import sys

from .numbers import find_numbers, parse_number
from .scrapers import USER_AGENT

LO, HI = 1_000_000, 2_000_000_000  # تومان یا ریال


def walk(data, prefix=""):
    if isinstance(data, dict):
        for k, v in data.items():
            yield from walk(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(data, list):
        for i, v in enumerate(data[:50]):
            yield from walk(v, f"{prefix}.{i}" if prefix else str(i))
    else:
        num = parse_number(data) if isinstance(data, (int, float, str)) else None
        if num and LO <= num <= HI:
            yield prefix, data


async def discover(url: str, wait_ms: int = 8000) -> None:
    from playwright.async_api import async_playwright

    hits: list[tuple[str, str, object]] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(user_agent=USER_AGENT, locale="fa-IR")

        async def on_response(resp):
            if "json" not in (resp.headers.get("content-type") or ""):
                return
            try:
                data = await resp.json()
            except Exception:  # noqa: BLE001
                return
            for path, value in walk(data):
                hits.append((resp.url, path, value))

        page.on("response", on_response)
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(wait_ms)
        text = await page.inner_text("body")
        await browser.close()

    print("=== پاسخ‌های JSON حاوی عدد شبیه قیمت ===")
    for req_url, path, value in hits:
        print(f"{req_url}\n    path={path}  value={value}")
    if not hits:
        print("(هیچ)")
    print("\n=== اعداد بزرگ داخل متن صفحه (با ۴۰ کاراکتر قبلشان) ===")
    for pos, num in find_numbers(text):
        if LO <= num <= HI:
            context = text[max(0, pos - 40):pos].replace("\n", " ")
            print(f"{num:>15,.0f}   ← …{context}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(discover(sys.argv[1]))
