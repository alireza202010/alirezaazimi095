import json
from pathlib import Path

from trip.models import Destination


def load_destinations(path: Path) -> list[Destination]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    destinations = [Destination(**d) for d in raw["destinations"]]
    ids = [d.id for d in destinations]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate destination ids")
    return destinations
