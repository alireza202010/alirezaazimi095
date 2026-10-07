"""Generate a deterministic SAMPLE publisher inventory (fictional .example domains).

The numbers are realistic in shape only. Replace data/publishers.csv with real
publisher data (via the UI import or by editing the CSV) before real use.

    python scripts/generate_sample_data.py > data/publishers.csv
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.catalog import CATEGORIES  # noqa: E402
from app.data import to_csv  # noqa: E402
from app.models import Publisher  # noqa: E402

WORDS = ["نوین", "برتر", "امروز", "پلاس", "آنلاین", "روز", "پارس", "مرجع", "هوشمند", "سبز"]
SLUGS = ["novin", "bartar", "emrooz", "plus", "online", "rooz", "pars", "marja", "hoosh", "sabz"]
SPECIFIC = [c for c in CATEGORIES if c != "general"]

# type: (count, price range toman, authority range, traffic range, outbound range, products)
PROFILES = {
    "news_agency": (10, (15_000_000, 60_000_000), (60, 90), (2_000_000, 30_000_000), (30, 120), ["news_reportage", "reportage"]),
    "news": (25, (3_000_000, 15_000_000), (35, 70), (100_000, 3_000_000), (10, 60), ["reportage", "news_reportage"]),
    "niche": (70, (1_000_000, 8_000_000), (20, 55), (10_000, 800_000), (2, 30), ["reportage", "guest_post", "backlink"]),
    "blog": (30, (300_000, 2_000_000), (10, 35), (1_000, 80_000), (1, 20), ["guest_post", "backlink"]),
    "directory": (15, (100_000, 800_000), (5, 30), (500, 20_000), (20, 200), ["directory_listing", "backlink"]),
}


def round_price(p: float) -> int:
    return int(round(p / 50_000) * 50_000) or 50_000


def log_uniform(rng: random.Random, lo: int, hi: int) -> int:
    return int(lo * (hi / lo) ** rng.random())


def generate(seed: int = 42) -> list[Publisher]:
    rng = random.Random(seed)
    pubs: list[Publisher] = []
    n = 0
    for ptype, (count, price_r, auth_r, traffic_r, out_r, products) in PROFILES.items():
        for _ in range(count):
            n += 1
            w = rng.randrange(len(WORDS))
            if ptype in {"news_agency", "news"}:
                cats = ["general"] + rng.sample(SPECIFIC, rng.randint(0, 2))
                label = "خبرگزاری" if ptype == "news_agency" else "اخبار"
                name = f"{label} {WORDS[w]} {n}"
                slug = f"{'agency' if ptype == 'news_agency' else 'news'}-{SLUGS[w]}{n}"
            else:
                cats = rng.sample(SPECIFIC, rng.randint(1, 2))
                label = {"niche": "مجله", "blog": "وبلاگ", "directory": "نیازمندی"}[ptype]
                name = f"{label} {CATEGORIES[cats[0]]} {WORDS[w]}"
                slug = f"{cats[0].replace('_', '-')}-{SLUGS[w]}{n}"

            authority = rng.randint(*auth_r)
            traffic = log_uniform(rng, *traffic_r)
            outbound = rng.randint(*out_r)
            if rng.random() < 0.12:  # link-farm pattern: inflated authority, little traffic, many posts
                authority = min(95, authority + 25)
                traffic = max(500, traffic // 50)
                outbound = outbound * 4 + 40

            pubs.append(Publisher(
                id=f"P{n:04d}",
                name=name,
                domain=f"{slug}.example",
                type=ptype,
                categories=cats,
                product=rng.choice(products),
                price=round_price(rng.uniform(*price_r) * (0.6 + authority / 100)),
                authority=authority,
                monthly_traffic=traffic,
                outbound_per_month=outbound,
                index_rate=round(rng.uniform(0.55, 1.0), 2),
                link_type=rng.choices(["dofollow", "nofollow", "sponsored"], [0.82, 0.1, 0.08])[0],
                permanent=rng.random() < 0.8,
            ))
    return pubs


if __name__ == "__main__":
    sys.stdout.write(to_csv(generate()))
