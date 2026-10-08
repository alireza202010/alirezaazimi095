"""AI enrichment: a small Claude agent researches each lead on the web.

For every lead it searches the web (Instagram pages, the shop's site, map listings,
business directories), then reports back through the ``submit_lead_info`` tool:
phones, Instagram, website, shop type, size, branches and a short Persian note
for the salesperson. Results are cached per lead so re-runs don't pay twice.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .models import Lead
from .text import normalize_instagram, normalize_phone, split_phones

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"
SUBMIT_TOOL = "submit_lead_info"

SHOP_TYPES = {
    "retail": "خرده‌فروشی",
    "wholesale": "عمده‌فروشی / پخش",
    "workshop": "کارگاه / سازنده",
    "gallery": "گالری / برند",
    "coin_dealer": "سکه و طلای آب‌شده",
    "unknown": "",
}

SUBMIT_TOOL_DEF = {
    "name": SUBMIT_TOOL,
    "description": (
        "Report what you found about this gold shop. Call it exactly once, when your research is done. "
        "Leave a field empty (\"\" / []) or 'unknown' when you could not verify it."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "found": {"type": "boolean", "description": "true if you found sources that clearly refer to this exact shop"},
            "landline_phones": {"type": "array", "items": {"type": "string"}, "description": "Landline numbers, e.g. 02155667788"},
            "mobile_phones": {"type": "array", "items": {"type": "string"}, "description": "Mobile/WhatsApp numbers, e.g. 09121234567"},
            "instagram": {"type": "string", "description": "Instagram page URL or @handle of this shop"},
            "website": {"type": "string", "description": "Official website URL"},
            "shop_type": {"type": "string", "enum": list(SHOP_TYPES)},
            "size": {"type": "string", "enum": ["small", "medium", "large", "unknown"]},
            "branches": {"type": "integer", "description": "Number of branches you saw evidence for; 0 if unknown"},
            "sales_note": {
                "type": "string",
                "description": "1-2 Persian sentences for the salesperson: what this shop is like and a good opening angle.",
            },
            "evidence_urls": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "found", "landline_phones", "mobile_phones", "instagram", "website",
            "shop_type", "size", "branches", "sales_note", "evidence_urls",
        ],
        "additionalProperties": False,
    },
}

SYSTEM_PROMPT = """You research gold and jewellery shops in Tehran for the B2B sales team of {business}.
{business_context}

Your job for each shop: find its public business contact details and a quick profile, so a salesperson
can call it. Search the web (in Persian and English): the shop's Instagram page, its website, Google Maps,
Neshan or Balad listings, and Iranian business directories.

Rules:
- Only report details that clearly belong to THIS shop (same name and same area/address). Chains have
  several branches; prefer the branch at the given address, and count branches if you see them.
- Never guess or construct a phone number. A number must appear in a source you actually read.
- Business phones published by the shop itself are fine to report; do not dig for owners' private data.
- Estimate size from evidence (Instagram followers, number of branches, reviews, showroom vs. small booth).
- When done, call {tool} once. If you find nothing reliable, call it with found=false and empty fields."""

USER_PROMPT = """Gold shop to research:
- Name: {name}
- Address: {address}
- Neighbourhood / district: {neighbourhood} / {district}
- Known phones: {phones}
- Known Instagram / website: {instagram} {website}
- Map location: {location}"""


class Enricher:
    def __init__(
        self,
        client=None,
        model: str = DEFAULT_MODEL,
        effort: str = "medium",
        business: str = "Hashin Gold (هاشین گلد)",
        business_context: str = "",
        max_searches: int = 5,
        workers: int = 4,
        cache_file: Path | None = None,
    ):
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self.client = client
        self.model = model
        self.effort = effort
        self.workers = workers
        self.system = SYSTEM_PROMPT.format(
            business=business, business_context=business_context.strip(), tool=SUBMIT_TOOL
        )
        self.tools = [
            {"type": "web_search_20260209", "name": "web_search", "max_uses": max_searches},
            SUBMIT_TOOL_DEF,
        ]
        self.cache_file = cache_file
        self.cache: dict[str, dict] = {}
        if cache_file and cache_file.exists():
            self.cache = json.loads(cache_file.read_text(encoding="utf-8"))

    def _create(self, messages: list):
        return self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=self.system,
            tools=self.tools,
            messages=messages,
            output_config={"effort": self.effort},
            # If a safety classifier declines, Anthropic re-runs the request on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )

    def research(self, lead: Lead, max_turns: int = 6) -> dict | None:
        """Run the agent loop for one lead; returns the submit_lead_info input or None."""
        prompt = USER_PROMPT.format(
            name=lead.name,
            address=lead.address or "-",
            neighbourhood=lead.neighbourhood or "-",
            district=lead.district_label,
            phones=", ".join(lead.phones) or "-",
            instagram=lead.instagram or "-",
            website=lead.website or "",
            location=lead.maps_url or "-",
        )
        messages: list = [{"role": "user", "content": prompt}]
        for _ in range(max_turns):
            resp = self._create(messages)
            if resp.stop_reason == "refusal":
                log.warning("Enrichment refused for %s", lead.name)
                return None
            for block in resp.content:
                if block.type == "tool_use" and block.name == SUBMIT_TOOL:
                    return dict(block.input)
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason == "pause_turn":  # long server-side search turn; let it continue
                continue
            messages.append({"role": "user", "content": f"Please call {SUBMIT_TOOL} now with what you found."})
        log.warning("Enrichment gave no result for %s", lead.name)
        return None

    @staticmethod
    def apply(lead: Lead, info: dict) -> None:
        lead.enriched = True
        if not info.get("found"):
            return
        phones = [p for p in (normalize_phone(x) for x in info.get("landline_phones", []) + info.get("mobile_phones", [])) if p]
        landlines, mobiles = split_phones(phones)
        lead.add_phones(landlines, mobiles)
        lead.instagram = lead.instagram or normalize_instagram(info.get("instagram"))
        website = (info.get("website") or "").strip()
        if not lead.website and website.startswith("http") and "instagram.com" not in website:
            lead.website = website
        lead.shop_type = SHOP_TYPES.get(info.get("shop_type", ""), "")
        lead.size = info.get("size", "") if info.get("size") != "unknown" else ""
        lead.branches = max(0, int(info.get("branches") or 0))
        lead.ai_note = (info.get("sales_note") or "").strip()
        if "web" not in lead.sources:
            lead.sources.append("web")

    def enrich(self, leads: list[Lead], limit: int = 50, refresh: bool = False) -> int:
        """Enrich up to ``limit`` leads; leads without any phone go first. Returns how many were researched."""
        for lead in leads:  # re-apply cached research from earlier runs for free
            if not refresh and lead.lead_id in self.cache:
                self.apply(lead, self.cache[lead.lead_id])
        todo = [l for l in leads if not l.enriched and l.business_status != "CLOSED_PERMANENTLY"]
        todo.sort(key=lambda l: (bool(l.phones), bool(l.instagram), -(l.reviews or 0)))
        todo = todo[:limit]
        log.info("Enriching %d leads with %s", len(todo), self.model)

        def work(lead: Lead):
            try:
                return lead, self.research(lead)
            except Exception as exc:
                log.warning("Enrichment failed for %s: %s", lead.name, exc)
                return lead, None

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            for lead, info in pool.map(work, todo):
                if info is not None:
                    self.cache[lead.lead_id] = info
                    self.apply(lead, info)
        if self.cache_file:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), encoding="utf-8")
        return len(todo)
