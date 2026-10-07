import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from trip import catalog
from trip.data import load_destinations
from trip.models import Destination, TripRequest, TripResponse
from trip.recommender import recommend

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA = BASE_DIR.parent / "data" / "destinations.json"
# Toman per US dollar shown as the default in the UI; users should enter today's rate.
DEFAULT_USD_RATE = int(os.environ.get("DEFAULT_USD_RATE", "100000"))


def create_app(data_path: Path | None = None) -> FastAPI:
    destinations = load_destinations(data_path or Path(os.environ.get("DESTINATIONS_JSON", DEFAULT_DATA)))
    app = FastAPI(title="سفرپلنر - پیشنهاددهنده هوشمند سفر")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(BASE_DIR / "static" / "index.html")

    @app.get("/api/meta")
    def meta() -> dict:
        return {
            "interests": catalog.INTERESTS,
            "traveler_types": catalog.TRAVELER_TYPES,
            "scopes": catalog.SCOPES,
            "comfort_levels": catalog.COMFORT_LEVELS,
            "default_usd_rate": DEFAULT_USD_RATE,
        }

    @app.get("/api/destinations", response_model=list[Destination])
    def list_destinations() -> list[Destination]:
        return destinations

    @app.post("/api/recommend", response_model=TripResponse)
    def recommend_trip(req: TripRequest) -> TripResponse:
        return recommend(req, destinations)

    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    return app


app = create_app()
