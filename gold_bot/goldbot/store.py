"""ذخیره تاریخچه قیمت‌ها در SQLite برای نمایش تغییرات و جلوگیری از پست تکراری."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .scrapers import Quote


class Store:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS quotes (
                ts INTEGER NOT NULL, key TEXT NOT NULL, buy REAL, sell REAL
            );
            CREATE INDEX IF NOT EXISTS quotes_key_ts ON quotes(key, ts);
            CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
            """
        )

    def last(self) -> dict[str, tuple[float | None, float | None]]:
        rows = self.db.execute(
            """SELECT q.key, q.buy, q.sell FROM quotes q
               JOIN (SELECT key, MAX(ts) ts FROM quotes GROUP BY key) m
               ON q.key = m.key AND q.ts = m.ts"""
        ).fetchall()
        return {k: (b, s) for k, b, s in rows}

    def save(self, quotes: list[Quote], ts: int | None = None) -> None:
        ts = ts or int(time.time())
        self.db.executemany(
            "INSERT INTO quotes VALUES (?, ?, ?, ?)",
            [(ts, q.key, q.buy, q.sell) for q in quotes if q.ok],
        )
        self.db.commit()

    def get(self, k: str) -> str | None:
        row = self.db.execute("SELECT v FROM kv WHERE k = ?", (k,)).fetchone()
        return row[0] if row else None

    def set(self, k: str, v: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)", (k, v))
        self.db.commit()
