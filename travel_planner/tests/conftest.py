import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trip.main import create_app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    return TestClient(create_app())


@pytest.fixture
def trip():
    return {
        "budget": 150_000_000,
        "start_date": "2026-11-05",
        "end_date": "2026-11-10",
        "adults": 2,
        "children": 0,
        "traveler_type": "couple",
        "interests": ["history", "food"],
        "usd_rate": 100_000,
    }
