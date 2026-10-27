import asyncio
import json
from datetime import datetime

import httpx

from goldbot.config import Settings
from goldbot.formatter import TEHRAN, build_message, jalali_stamp, prices_changed
from goldbot.main import in_quiet_hours
from goldbot.scrapers import Quote
from goldbot.store import Store
from goldbot.telegram import Telegram

NOW = datetime(2026, 10, 27, 14, 30, tzinfo=TEHRAN)


def quotes():
    return [
        Quote("a", "پلتفرم الف", 7_300_000, 7_200_000),
        Quote("b", "پلتفرم ب", 7_250_000, 7_150_000),
        Quote("c", "پلتفرم ج", error="Timeout"),
    ]


def test_jalali_stamp():
    assert jalali_stamp(NOW) == "سه‌شنبه ۵ آبان ۱۴۰۵ — ساعت ۱۴:۳۰"


def test_message_sorted_and_summary():
    msg = build_message(quotes(), {"a": (7_000_000, 7_200_000)}, now=NOW, handle="@ch")
    assert msg.index("پلتفرم ب") < msg.index("پلتفرم الف")
    assert "ارزان‌ترین خرید: <b>پلتفرم ب</b>" in msg
    assert "بهترین فروش: <b>پلتفرم الف</b>" in msg
    assert "🔺۴.۲۹٪" in msg
    assert "در دسترس نبود: پلتفرم ج" in msg
    assert msg.endswith("@ch")


def test_store_and_change_detection():
    store = Store(":memory:")
    qs = quotes()
    assert prices_changed(qs, store.last())
    store.save(qs, ts=1)
    assert store.last() == {"a": (7_300_000, 7_200_000), "b": (7_250_000, 7_150_000)}
    assert not prices_changed(qs, store.last())
    store.set("k", "v")
    assert store.get("k") == "v"


def test_quiet_hours():
    s = Settings(quiet_hours=(0, 8))
    assert in_quiet_hours(s, datetime(2026, 10, 27, 3, tzinfo=TEHRAN))
    assert not in_quiet_hours(s, NOW)
    s = Settings(quiet_hours=(23, 7))
    assert in_quiet_hours(s, datetime(2026, 10, 27, 23, 30, tzinfo=TEHRAN))


def test_telegram_send_and_edit():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append((request.url.path, body))
        if request.url.path.endswith("editMessageText"):
            return httpx.Response(200, json={"ok": False, "description": "Bad Request: message is not modified"})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})

    async def run():
        tg = Telegram("TOKEN", "https://relay.example", transport=httpx.MockTransport(handler))
        assert await tg.send("@ch", "hi") == 42
        await tg.edit("@ch", 42, "hi")  # «not modified» نباید خطا بدهد
        await tg.close()

    asyncio.run(run())
    assert calls[0][0] == "/botTOKEN/sendMessage"
    assert calls[0][1]["parse_mode"] == "HTML"
