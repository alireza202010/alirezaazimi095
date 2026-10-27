"""اجرای بات.

  python -m goldbot check   # فقط قیمت‌ها را بگیر و چاپ کن (بدون تلگرام) — برای تست پلتفرم‌ها
  python -m goldbot once    # یک‌بار بگیر و در کانال پست کن (مناسب cron)
  python -m goldbot run     # سرویس دائمی: هر INTERVAL_MINUTES دقیقه پست + پاسخ به /price
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime

from .config import Settings, load_platforms
from .formatter import TEHRAN, build_message, prices_changed
from .scrapers import fetch_all
from .store import Store
from .telegram import Telegram

log = logging.getLogger("goldbot")

HELP = ("سلام! 👋\nمن قیمت لحظه‌ای طلای ۱۸ عیار را از پلتفرم‌های آنلاین طلا مقایسه می‌کنم.\n"
        "/price — آخرین قیمت‌ها")


def in_quiet_hours(settings: Settings, now: datetime) -> bool:
    if not settings.quiet_hours:
        return False
    start, end = settings.quiet_hours
    h = now.astimezone(TEHRAN).hour
    return start <= h < end if start <= end else (h >= start or h < end)


async def collect(settings: Settings, store: Store) -> tuple[str, bool]:
    quotes = await fetch_all(load_platforms(), settings)
    previous = store.last()
    changed = prices_changed(quotes, previous)
    text = build_message(quotes, previous, title=settings.channel_title, handle=settings.channel_handle)
    store.save(quotes)
    store.set("last_text", text)
    return text, changed


async def publish(settings: Settings, store: Store, tg: Telegram) -> None:
    if in_quiet_hours(settings, datetime.now(TEHRAN)):
        log.info("ساعت سکوت؛ پست نمی‌شود")
        return
    text, changed = await collect(settings, store)
    if settings.only_on_change and not changed:
        log.info("قیمتی تغییر نکرده؛ پست نمی‌شود")
        return
    last_id = store.get("last_message_id")
    if settings.edit_last_message and last_id:
        await tg.edit(settings.channel_id, int(last_id), text)
    else:
        store.set("last_message_id", str(await tg.send(settings.channel_id, text)))
    log.info("پیام منتشر شد")


async def scheduler(settings: Settings, store: Store, tg: Telegram) -> None:
    while True:
        try:
            await publish(settings, store, tg)
        except Exception:  # noqa: BLE001
            log.exception("خطا در انتشار")
        await asyncio.sleep(settings.interval_minutes * 60)


async def commands(settings: Settings, store: Store, tg: Telegram) -> None:
    offset = None
    while True:
        try:
            for upd in await tg.updates(offset):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                text = (msg.get("text") or "").split("@")[0].strip()
                chat = msg.get("chat", {}).get("id")
                if not chat:
                    continue
                if text == "/price":
                    await tg.send(chat, store.get("last_text") or "هنوز قیمتی دریافت نشده؛ چند دقیقه دیگر امتحان کنید.")
                elif text in ("/start", "/help"):
                    await tg.send(chat, HELP)
        except Exception:  # noqa: BLE001
            log.exception("خطا در دریافت پیام‌ها")
            await asyncio.sleep(5)


async def amain(mode: str) -> None:
    settings = Settings.from_env()
    store = Store(settings.db_path)
    if mode == "check":
        quotes = await fetch_all(load_platforms(), settings)
        for q in quotes:
            print(f"{q.key:12} buy={q.buy} sell={q.sell} error={q.error}")
        print()
        print(build_message(quotes, store.last(), title=settings.channel_title))
        return

    tg = Telegram(settings.bot_token, settings.telegram_api_base, settings.proxy)
    try:
        if mode == "once":
            await publish(settings, store, tg)
        else:
            await asyncio.gather(scheduler(settings, store, tg), commands(settings, store, tg))
    finally:
        await tg.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="goldbot")
    parser.add_argument("mode", choices=["check", "once", "run"], nargs="?", default="run")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(amain(args.mode))


if __name__ == "__main__":
    main()
