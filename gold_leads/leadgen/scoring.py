"""Lead score (0-100) and tier, so the sales team calls the best leads first.

The score rewards how *reachable* a shop is (phone, mobile, Instagram) and how
*big/active* it looks (Google reviews, branches, AI size estimate).
Tune the weights here to match Hashin Gold's ideal customer.
"""

from __future__ import annotations

from .models import Lead

TIER_A = 60
TIER_B = 35


def score_lead(lead: Lead) -> int:
    if lead.business_status == "CLOSED_PERMANENTLY":
        return 0
    score = 0
    score += 25 if lead.landlines else 0
    score += 20 if lead.mobiles else 0
    score += 10 if lead.instagram else 0
    score += 5 if lead.website else 0
    reviews = lead.reviews or 0
    score += 15 if reviews >= 200 else 10 if reviews >= 50 else 5 if reviews >= 10 else 0
    if lead.rating and lead.rating >= 4.3 and reviews >= 10:
        score += 5
    score += min(10, 5 * (len(lead.sources) - 1))  # confirmed by several map sources
    score += {"large": 15, "medium": 8}.get(lead.size, 0)
    score += 5 if lead.branches and lead.branches > 1 else 0
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
