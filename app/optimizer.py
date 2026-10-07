"""Budget-constrained selection: a multiple-choice (grouped) knapsack.

Offers are grouped by domain and at most one offer per domain is picked, so the
plan never buys two links from the same site. Prices are rounded *up* to a
budget unit, which guarantees the real total never exceeds the budget.
"""

import math
from collections import defaultdict

from app.scoring import Scored

MAX_UNITS = 2000


def budget_unit(budget: int) -> int:
    return max(10_000, math.ceil(budget / MAX_UNITS))


def group_knapsack(
    items: list[Scored], budget: int, unit: int | None = None, slot_cost: float = 0.0
) -> list[Scored]:
    """Maximize total `power - slot_cost` under the budget, one offer per domain.

    `slot_cost` is a fixed charge per link; raising it trades many weak links for
    fewer strong ones, which is how the planner enforces link-velocity caps.
    """
    items = [it for it in items if it.power - slot_cost > 0]
    if budget <= 0 or not items:
        return []
    unit = unit or budget_unit(budget)
    capacity = budget // unit

    groups: dict[str, list[Scored]] = defaultdict(list)
    for it in items:
        groups[it.pub.domain].append(it)
    group_list = list(groups.values())

    # best[b] = best total quality with cost <= b units.
    best = [0.0] * (capacity + 1)
    history: list[tuple[list[int], list[int]]] = []
    for group in group_list:
        costs = [math.ceil(it.pub.price / unit) for it in group]
        new_best = best[:]
        choice = [-1] * (capacity + 1)
        for idx, (it, cost) in enumerate(zip(group, costs)):
            if cost > capacity:
                continue
            for b in range(cost, capacity + 1):
                candidate = best[b - cost] + it.power - slot_cost
                if candidate > new_best[b] + 1e-9:
                    new_best[b] = candidate
                    choice[b] = idx
        best = new_best
        history.append((choice, costs))

    chosen: list[Scored] = []
    b = capacity
    for g in range(len(group_list) - 1, -1, -1):
        choice, costs = history[g]
        idx = choice[b]
        if idx >= 0:
            chosen.append(group_list[g][idx])
            b -= costs[idx]
    chosen.reverse()
    return chosen
