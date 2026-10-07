import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

SAMPLE_CSV = Path(__file__).resolve().parent.parent / "data" / "publishers.csv"


@pytest.fixture
def client(tmp_path):
    csv_path = tmp_path / "publishers.csv"
    shutil.copy(SAMPLE_CSV, csv_path)
    return TestClient(create_app(csv_path))


@pytest.fixture
def plan_request():
    return {
        "site_url": "https://www.digishop.ir",
        "brand_name": "دیجی‌شاپ",
        "budget": 80_000_000,
        "months": 3,
        "category": "ecommerce",
        "keywords": [
            {"keyword": "خرید گوشی", "url": "https://digishop.ir/mobile"},
            {"keyword": "لپ تاپ", "url": "https://digishop.ir/laptop"},
        ],
    }
