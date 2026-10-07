import asyncio
from datetime import date

import httpx
import pytest

from app.site_audit import SiteAuditor, UnsafeUrlError

HOME = """<html lang="fa"><head><title>فروشگاه نمونه</title>
<meta name="description" content="خرید آنلاین"></head>
<body><script>var x = "not counted words here";</script>
<p>متن صفحه اصلی فروشگاه</p><a href="/mobile">موبایل</a><a href="https://other.com/">x</a></body></html>"""


def handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    host = request.url.host
    if host == "rdap.org":
        return httpx.Response(200, json={"events": [{"eventAction": "registration", "eventDate": "2020-10-07T00:00:00Z"}]})
    if host == "web.archive.org":
        return httpx.Response(200, json=[["timestamp"], ["20180315120000"]])
    if host == "openpagerank.com":
        assert request.headers["API-OPR"] == "key"
        return httpx.Response(200, json={"response": [{"page_rank_decimal": 3.4}]})
    if url == "http://shop.ir/":
        return httpx.Response(301, headers={"location": "https://shop.ir/"})
    if url == "https://shop.ir/":
        return httpx.Response(200, html=HOME)
    if url == "https://shop.ir/robots.txt":
        return httpx.Response(200, text="User-agent: *")
    if url == "https://shop.ir/mobile":
        return httpx.Response(200, html="<html><head><title>موبایل</title></head></html>")
    if url == "https://shop.ir/old":
        return httpx.Response(200, html='<meta name="robots" content="noindex,follow">')
    return httpx.Response(404)


async def public_resolver(host: str) -> list[str]:
    return {"evil.ir": ["127.0.0.1"]}.get(host, ["93.184.216.34"])


def run(coro):
    return asyncio.run(coro)


def auditor(client, key="key"):
    return SiteAuditor(client, resolver=public_resolver, today=date(2026, 10, 7), opr_api_key=key)


def test_full_audit():
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await auditor(client).analyze(
                "http://shop.ir/", ["https://shop.ir/mobile", "https://shop.ir/old", "https://shop.ir/gone", "https://x.com/a"]
            )

    a = run(go())
    assert a.reachable and a.https and a.indexable and a.final_url == "https://shop.ir/"
    assert a.title == "فروشگاه نمونه" and a.meta_description == "خرید آنلاین" and a.lang == "fa"
    assert a.has_robots_txt and not a.has_sitemap
    assert a.internal_links == 1 and a.external_links == 1
    assert a.word_count == 6  # script content excluded
    assert a.domain_created == date(2020, 10, 7) and a.domain_age_years == 6.0
    assert a.first_archived == date(2018, 3, 15) and a.history_years == 8.6
    assert a.authority == 34 and a.authority_source == "OpenPageRank"

    pages = {t.url: t for t in a.target_pages}
    assert pages["https://shop.ir/mobile"].indexable
    assert "noindex" in pages["https://shop.ir/old"].issue
    assert pages["https://shop.ir/gone"].status_code == 404 and not pages["https://shop.ir/gone"].indexable
    assert pages["https://x.com/a"].issue == "صفحه روی دامنه دیگری است"

    checks = {c.key: c.status for c in a.checks}
    assert checks["reachable"] == "ok" and checks["targets"] == "fail" and checks["sitemap"] == "warn"
    assert 0 < a.readiness < 100


def test_external_sources_fail_gracefully():
    def broken(request):
        if request.url.host in {"rdap.org", "web.archive.org"}:
            raise httpx.ConnectError("blocked")
        return handler(request)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(broken)) as client:
            return await auditor(client, key="").analyze("https://shop.ir", [])

    a = run(go())
    assert a.reachable and a.domain_created is None and a.first_archived is None and a.authority is None
    assert set(a.sources_failed) == {"RDAP", "Wayback Machine"}


def test_unreachable_site():
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as client:
            return await auditor(client).analyze("https://down.ir", [])

    a = run(go())
    assert not a.reachable and a.checks[0].status == "fail" and a.readiness == 0


def test_blocks_private_addresses_including_redirects():
    def redirecting(request):
        if request.url.host == "shop.ir":
            return httpx.Response(302, headers={"location": "http://evil.ir/admin"})
        return httpx.Response(200, text="secret")

    async def go(url):
        async with httpx.AsyncClient(transport=httpx.MockTransport(redirecting)) as client:
            return await auditor(client).fetch(url)

    for url in ["http://evil.ir/", "https://shop.ir/", "file:///etc/passwd"]:
        with pytest.raises(UnsafeUrlError):
            run(go(url))


def test_analyze_endpoint_uses_analyzer(client):
    seen = {}

    async def fake(site_url, target_urls):
        seen["args"] = (site_url, target_urls)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await auditor(c).analyze(site_url, target_urls)

    client.app.state.analyzer = fake
    res = client.post("/api/site/analyze", json={"site_url": "https://shop.ir/", "target_urls": ["https://shop.ir/mobile"]})
    assert res.status_code == 200
    assert res.json()["authority"] == 34
    assert seen["args"] == ("https://shop.ir/", ["https://shop.ir/mobile"])
