"""Publisher inventory: CSV parsing and an in-memory store backed by a CSV file."""

import csv
import io
import threading
from pathlib import Path

from pydantic import ValidationError

from app.models import Publisher

CSV_COLUMNS = [
    "id", "name", "domain", "type", "categories", "product", "price", "authority",
    "monthly_traffic", "outbound_per_month", "index_rate", "link_type", "permanent",
]

_TRUE = {"1", "true", "yes", "y", "بله", "دائمی"}


class CsvImportError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _row_to_publisher(row: dict[str, str]) -> Publisher:
    return Publisher(
        id=row["id"].strip(),
        name=row["name"].strip(),
        domain=row["domain"].strip().lower(),
        type=row["type"].strip(),
        categories=[c.strip() for c in row["categories"].split("|") if c.strip()],
        product=row["product"].strip(),
        price=int(float(row["price"])),
        authority=int(float(row["authority"])),
        monthly_traffic=int(float(row["monthly_traffic"])),
        outbound_per_month=int(float(row["outbound_per_month"])),
        index_rate=float(row["index_rate"]),
        link_type=row["link_type"].strip(),
        permanent=row["permanent"].strip().lower() in _TRUE,
    )


def parse_csv(text: str) -> list[Publisher]:
    """Parse inventory CSV text. Raises CsvImportError listing every bad row."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    missing = [c for c in CSV_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise CsvImportError([f"missing columns: {', '.join(missing)}"])

    publishers: list[Publisher] = []
    errors: list[str] = []
    seen: set[str] = set()
    for line_no, row in enumerate(reader, start=2):
        try:
            pub = _row_to_publisher(row)
        except (ValidationError, ValueError, KeyError, AttributeError) as exc:
            errors.append(f"line {line_no}: {exc}".splitlines()[0])
            continue
        if pub.id in seen:
            errors.append(f"line {line_no}: duplicate id {pub.id}")
            continue
        seen.add(pub.id)
        publishers.append(pub)
    if errors:
        raise CsvImportError(errors)
    return publishers


def to_csv(publishers: list[Publisher]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for p in publishers:
        row = p.model_dump()
        row["categories"] = "|".join(p.categories)
        row["permanent"] = "true" if p.permanent else "false"
        writer.writerow(row)
    return buf.getvalue()


class PublisherStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._publishers: list[Publisher] = []
        if path.exists():
            self._publishers = parse_csv(path.read_text(encoding="utf-8"))

    def all(self) -> list[Publisher]:
        return list(self._publishers)

    def replace(self, publishers: list[Publisher]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(to_csv(publishers), encoding="utf-8")
            self._publishers = list(publishers)
