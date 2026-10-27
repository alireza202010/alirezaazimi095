"""کلاینت حداقلی Bot API تلگرام (بدون کتابخانه اضافه)."""
from __future__ import annotations

import httpx


class TelegramError(RuntimeError):
    pass


class Telegram:
    def __init__(self, token: str, api_base: str = "https://api.telegram.org",
                 proxy: str | None = None, transport: httpx.AsyncBaseTransport | None = None):
        if not token:
            raise TelegramError("BOT_TOKEN تنظیم نشده است")
        self.base = f"{api_base.rstrip('/')}/bot{token}"
        self.client = httpx.AsyncClient(timeout=40, proxy=proxy, transport=transport)

    async def call(self, method: str, **params):
        resp = await self.client.post(f"{self.base}/{method}", json=params)
        data = resp.json()
        if not data.get("ok"):
            raise TelegramError(f"{method}: {data.get('description')}")
        return data["result"]

    async def send(self, chat_id, text: str) -> int:
        result = await self.call("sendMessage", chat_id=chat_id, text=text,
                                 parse_mode="HTML", disable_web_page_preview=True)
        return result["message_id"]

    async def edit(self, chat_id, message_id: int, text: str) -> None:
        try:
            await self.call("editMessageText", chat_id=chat_id, message_id=message_id, text=text,
                            parse_mode="HTML", disable_web_page_preview=True)
        except TelegramError as exc:
            if "message is not modified" not in str(exc):
                raise

    async def updates(self, offset: int | None, timeout: int = 25) -> list[dict]:
        return await self.call("getUpdates", offset=offset, timeout=timeout,
                               allowed_updates=["message"])

    async def close(self) -> None:
        await self.client.aclose()
