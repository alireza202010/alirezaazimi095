"""تست واقعی مسیر browser با یک سایت محلی (اگر Playwright نصب نباشد رد می‌شود)."""
import asyncio
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from goldbot.config import Platform, Settings
from goldbot.discover import walk
from goldbot.scrapers import fetch_all

pytest.importorskip("playwright")

SPA = """<html><head><meta charset="utf-8"></head><body><div id=app>در حال بارگذاری</div><script>
fetch('/api/price').then(r => r.json()).then(d => {
  document.getElementById('app').innerText = 'قیمت خرید ' + d.data.buy.toLocaleString('fa-IR') +
      ' ریال  قیمت فروش ' + d.data.sell.toLocaleString('fa-IR') + ' ریال';
});
</script></body></html>"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("site")
    (root / "index.html").write_text(SPA, encoding="utf-8")
    (root / "api").mkdir()
    (root / "api" / "price").write_text(json.dumps({"data": {"buy": 72500000, "sell": 71000000}}))
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_browser_text_and_capture(site):
    platforms = [
        Platform("text", "متنی", site + "/index.html", unit="rial", wait_ms=1500),
        Platform("xhr", "XHR", site + "/index.html", unit="rial", wait_ms=1500,
                 capture_url_contains="/api/price", buy_path="data.buy", sell_path="data.sell"),
        Platform("api", "API", "", method="json", api_url=site + "/api/price", unit="rial",
                 buy_path="data.buy", sell_path="data.sell"),
    ]
    quotes = asyncio.run(fetch_all(platforms, Settings()))
    for q in quotes:
        assert (q.buy, q.sell) == (7_250_000, 7_100_000), q


def test_discover_walk():
    assert list(walk({"data": {"buy": 72500000, "x": 3}})) == [("data.buy", 72500000)]
