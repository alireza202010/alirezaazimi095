"""Lead score (0-100) and tier for recruiting representatives for Hashin's 750 gold bars.

The score asks two questions:
- *Fit* — would this shop be a good representative? Already selling bullion
  (شمش / آبشده / سکه), wholesale reach, size, branches, Instagram audience,
  and the AI's overall fit verdict.
- *Reachability* — can the sales team actually contact it? (phone, mobile, Instagram)
Tune the weights here as the team learns which shops sign up.
"""

from __future__ import annotations

from .models import Lead
from .text import has_bullion_hint

TIER_A = 60
TIER_B = 35


def score_lead(lead: Lead) -> int:
    if lead.business_status == "CLOSED_PERMANENTLY":
        return 0
    score = 0
    # Fit
    if lead.sells_bullion == "yes":
        score += 20
    elif lead.sells_bullion == "" and has_bullion_hint(lead.name, lead.category):
        score += 10  # name says آبشده / شمش / سکه, not yet verified
    score += 10 if lead.wholesale == "yes" else 0
    score += {"high": 20, "medium": 10}.get(lead.agency_fit, 0)
    score += {"large": 10, "medium": 5}.get(lead.size, 0)
    score += 5 if lead.branches and lead.branches > 1 else 0
    followers = lead.instagram_followers
    score += 10 if followers >= 50_000 else 5 if followers >= 10_000 else 0
    reviews = lead.reviews or 0
    score += 10 if reviews >= 200 else 5 if reviews >= 50 else 0
    # Reachability
    score += 15 if lead.landlines else 0
    score += 10 if lead.mobiles else 0
    score += 5 if lead.instagram else 0
    score += min(5, 5 * (len(lead.sources) - 1))  # confirmed by several sources
    if lead.business_status == "CLOSED_TEMPORARILY":
        score //= 2
    return min(score, 100)


def tier_for(score: int, lead: Lead) -> str:
    if lead.business_status == "CLOSED_PERMANENTLY":
        return "D"
    return "A" if score >= TIER_A else "B" if score >= TIER_B else "C"


def score_all(leads: list[Lead]) -> None:
    for lead in leads:
        lead.score = score_lead(lead)
        lead.tier = tier_for(lead.score, lead)
