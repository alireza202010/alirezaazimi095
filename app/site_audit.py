"""Automatic analysis of the client's site before planning.

Collects what can be detected without paid tools: reachability, HTTPS, speed,
indexability, basic on-page tags, robots.txt/sitemap, target-page health,
domain registration date (RDAP), online history (Wayback Machine) and, when an
OpenPageRank API key is configured, an authority score. Every external source
is optional: a failure leaves the field empty so the user can fill it in.
"""

import asyncio
import ipaddress
import os
import socket
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from app.anchors import domain_of
from app.jalali import fa_digits
from app.models import AuditCheck, SiteAudit, TargetPageStatus

USER_AGENT = "LinkPlannerBot/0.1 (+site audit)"
MAX_BODY_BYTES = 2_000_000
MAX_REDIRECTS = 5
TIMEOUT = httpx.Timeout(10.0, connect=5.0)

Resolver = Callable[[str], Awaitable[list[str]]]


class UnsafeUrlError(ValueError):
    pass


async def default_resolver(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


@dataclass
class Fetched:
    url: str
    status: int
    elapsed_ms: int
    headers: httpx.Headers
    body: str


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.meta_description: str | None = None
        self.robots: str = ""
        self.lang: str | None = None
        self.canonical: str | None = None
        self.links: list[str] = []
        self.words = 0
        self._in_title = False
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html" and a.get("lang"):
            self.lang = a["lang"].lower()
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = a.get("name", "").lower()
            if name == "description":
                self.meta_description = a.get("content", "").strip() or None
            elif name in {"robots", "googlebot"}:
                self.robots += " " + a.get("content", "").lower()
        elif tag == "link" and "canonical" in a.get("rel", "").lower():
            self.canonical = a.get("href") or None
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag in {"script", "style", "noscript", "template"}:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in {"script", "style", "noscript", "template"} and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._in_title:
            self.title = ((self.title or "") + data).strip() or None
        elif not self._skip:
            self.words += len(data.split())


def _years_since(d: date | None, today: date) -> float | None:
    return round((today - d).days / 365.25, 1) if d else None


class SiteAuditor:
    def __init__(
        self,
        client: httpx.AsyncClient,
        resolver: Resolver = default_resolver,
        today: date | None = None,
        opr_api_key: str | None = None,
    ):
        self.client = client
        self.resolver = resolver
        self.today = today or date.today()
        self.opr_api_key = opr_api_key if opr_api_key is not None else os.environ.get("OPENPAGERANK_API_KEY")

    async def _check_public(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise UnsafeUrlError("only http(s) URLs are allowed")
        try:
            addresses = await self.resolver(parsed.hostname)
        except OSError as exc:
            raise UnsafeUrlError(f"cannot resolve {parsed.hostname}") from exc
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise UnsafeUrlError("address is not public")

    async def fetch(self, url: str) -> Fetched:
        """GET a user-supplied URL, re-validating every redirect hop against private addresses."""
        for _ in range(MAX_REDIRECTS + 1):
            await self._check_public(url)
            start = time.perf_counter()
            async with self.client.stream(
                "GET", url, follow_redirects=False, headers={"User-Agent": USER_AGENT}
            ) as resp:
                if resp.is_redirect and "location" in resp.headers:
                    url = urljoin(url, resp.headers["location"])
                    continue
                body = bytearray()
                async for chunk in resp.aiter_bytes():
                    body.extend(chunk)
                    if len(body) >= MAX_BODY_BYTES:
                        break
                elapsed = int((time.perf_counter() - start) * 1000)
                text = body.decode(resp.encoding or "utf-8", errors="replace")
                return Fetched(str(resp.url), resp.status_code, elapsed, resp.headers, text)
        raise UnsafeUrlError("too many redirects")

    async def registration_date(self, domain: str) -> date | None:
        resp = await self.client.get(f"https://rdap.org/domain/{domain}", follow_redirects=True)
        if resp.status_code != 200:
            return None
        for event in resp.json().get("events", []):
            if event.get("eventAction") == "registration" and event.get("eventDate"):
                return datetime.fromisoformat(event["eventDate"].replace("Z", "+00:00")).date()
        return None

    async def first_archived(self, domain: str) -> date | None:
        resp = await self.client.get(
            "https://web.archive.org/cdx/search/cdx",
            params={"url": domain, "output": "json", "limit": "1", "fl": "timestamp"},
        )
        if resp.status_code != 200:
            return None
        rows = resp.json()
        if len(rows) < 2:  # first row is the header
            return None
        return datetime.strptime(rows[1][0][:8], "%Y%m%d").date()

    async def authority(self, domain: str) -> int | None:
        if not self.opr_api_key:
            return None
        resp = await self.client.get(
            "https://openpagerank.com/api/v1.0/getPageRank",
            params={"domains[]": domain},
            headers={"API-OPR": self.opr_api_key},
        )
        if resp.status_code != 200:
            return None
        rank = (resp.json().get("response") or [{}])[0].get("page_rank_decimal")
        return round(float(rank) * 10) if rank not in (None, "") else None

    async def _exists(self, url: str) -> bool:
        try:
            return (await self.fetch(url)).status == 200
        except (httpx.HTTPError, UnsafeUrlError):
            return False

    async def _target(self, url: str, site_domain: str) -> TargetPageStatus:
        if domain_of(url) != site_domain:
            return TargetPageStatus(url=url, indexable=False, issue="صفحه روی دامنه دیگری است")
        try:
            page = await self.fetch(url)
        except (httpx.HTTPError, UnsafeUrlError):
            return TargetPageStatus(url=url, indexable=False, issue="صفحه در دسترس نیست")
        parser = _PageParser()
        parser.feed(page.body)
        noindex = "noindex" in parser.robots or "noindex" in page.headers.get("x-robots-tag", "").lower()
        issue = None
        if page.status != 200:
            issue = f"کد وضعیت {fa_digits(page.status)}"
        elif noindex:
            issue = "noindex است و گوگل آن را ایندکس نمی‌کند"
        return TargetPageStatus(
            url=url, status_code=page.status, indexable=issue is None, title=parser.title, issue=issue
        )

    async def analyze(self, site_url: str, target_urls: list[str]) -> SiteAudit:
        site_url = site_url if "://" in site_url else f"https://{site_url}"
        if not urlparse(site_url).path:
            site_url += "/"
        domain = domain_of(site_url)
        failed: list[str] = []

        async def safe(name: str, coro):
            try:
                return await coro
            except (httpx.HTTPError, UnsafeUrlError, ValueError, KeyError, IndexError, TypeError):
                failed.append(name)
                return None

        home, registered, archived, authority = await asyncio.gather(
            safe("homepage", self.fetch(site_url)),
            safe("RDAP", self.registration_date(domain)),
            safe("Wayback Machine", self.first_archived(domain)),
            safe("OpenPageRank", self.authority(domain)),
        )
        # robots.txt and sitemap live on the final origin (after http->https / www redirects).
        final = urlparse(home.url if home else site_url)
        origin = f"{final.scheme}://{final.netloc}"
        robots_ok, sitemap_ok, *targets = await asyncio.gather(
            self._exists(f"{origin}/robots.txt"),
            self._exists(f"{origin}/sitemap.xml"),
            *(self._target(u, domain) for u in dict.fromkeys(target_urls)),
        )

        parser = _PageParser()
        if home:
            parser.feed(home.body)
        final_url = home.url if home else None
        internal = external = 0
        for href in parser.links:
            host = urlparse(urljoin(final_url or site_url, href)).netloc.lower().removeprefix("www.")
            if host == domain:
                internal += 1
            elif host:
                external += 1
        indexable = bool(home) and home.status == 200 and "noindex" not in parser.robots and (
            "noindex" not in home.headers.get("x-robots-tag", "").lower()
        )

        audit = SiteAudit(
            url=site_url,
            domain=domain,
            final_url=final_url,
            reachable=bool(home) and home.status == 200,
            status_code=home.status if home else None,
            https=(final_url or site_url).startswith("https://"),
            response_ms=home.elapsed_ms if home else None,
            title=parser.title,
            meta_description=parser.meta_description,
            lang=parser.lang,
            indexable=indexable,
            canonical=parser.canonical,
            has_robots_txt=bool(robots_ok),
            has_sitemap=bool(sitemap_ok),
            word_count=parser.words,
            internal_links=internal,
            external_links=external,
            domain_created=registered,
            domain_age_years=_years_since(registered, self.today),
            first_archived=archived,
            history_years=_years_since(archived, self.today),
            authority=authority,
            authority_source="OpenPageRank" if authority is not None else None,
            target_pages=list(targets),
            sources_failed=failed,
        )
        audit.checks = build_checks(audit)
        weights = {"ok": 1.0, "warn": 0.5, "fail": 0.0}
        audit.readiness = round(100 * sum(weights[c.status] for c in audit.checks) / len(audit.checks))
        return audit


def build_checks(a: SiteAudit) -> list[AuditCheck]:
    checks: list[AuditCheck] = []

    def add(key: str, label: str, status: str, detail: str) -> None:
        checks.append(AuditCheck(key=key, label=label, status=status, detail=detail))

    add("reachable", "در دسترس بودن سایت", "ok" if a.reachable else "fail",
        "سایت پاسخ 200 داد." if a.reachable else f"صفحه اصلی در دسترس نیست (کد {fa_digits(a.status_code or '—')}).")
    if not a.reachable:
        return checks
    add("https", "HTTPS", "ok" if a.https else "warn",
        "سایت روی HTTPS است." if a.https else "سایت HTTPS ندارد؛ قبل از لینک‌سازی SSL نصب کنید.")
    add("indexable", "قابلیت ایندکس", "ok" if a.indexable else "fail",
        "صفحه اصلی قابل ایندکس است." if a.indexable else "صفحه اصلی noindex است؛ لینک‌سازی بی‌اثر خواهد بود.")
    if a.response_ms is not None:
        status = "ok" if a.response_ms < 1500 else "warn"
        add("speed", "سرعت پاسخ سرور", status, f"زمان پاسخ حدود {fa_digits(f'{a.response_ms:,}')} میلی‌ثانیه.")
    add("title", "عنوان و توضیحات متا", "ok" if a.title and a.meta_description else "warn",
        "عنوان و توضیحات متا وجود دارد." if a.title and a.meta_description else "عنوان یا توضیحات متای صفحه اصلی خالی است.")
    add("robots", "فایل robots.txt", "ok" if a.has_robots_txt else "warn",
        "وجود دارد." if a.has_robots_txt else "پیدا نشد.")
    add("sitemap", "نقشه سایت (sitemap.xml)", "ok" if a.has_sitemap else "warn",
        "وجود دارد." if a.has_sitemap else "در /sitemap.xml پیدا نشد؛ ثبت نقشه سایت به ایندکس صفحات کمک می‌کند.")
    if a.word_count < 150:
        add("content", "محتوای صفحه اصلی", "warn", f"فقط حدود {fa_digits(a.word_count)} کلمه متن؛ صفحه اصلی کم‌محتواست.")
    bad = [t for t in a.target_pages if not t.indexable]
    if a.target_pages:
        add("targets", "سلامت صفحات هدف", "fail" if bad else "ok",
            f"{fa_digits(len(bad))} صفحه هدف مشکل دارد؛ قبل از خرید لینک اصلاح کنید." if bad else "همه صفحات هدف سالم و قابل ایندکس‌اند.")
    age = a.domain_age_years if a.domain_age_years is not None else a.history_years
    if age is not None:
        add("age", "عمر و سابقه دامنه", "ok" if age >= 1 else "warn",
            f"حدود {fa_digits(age)} سال سابقه." + ("" if age >= 1 else " دامنه جوان است؛ لینک‌سازی باید آرام و تدریجی باشد."))
    return checks


TOTAL_TIMEOUT_S = 40


async def analyze_site(site_url: str, target_urls: list[str]) -> SiteAudit:
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
        return await asyncio.wait_for(SiteAuditor(client).analyze(site_url, target_urls), TOTAL_TIMEOUT_S)
