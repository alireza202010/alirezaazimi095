import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from trip import catalog
from trip.data import load_destinations
from trip.guide import describe_choices, detect_city, guide, load_cities
from trip.guide_models import CitySummary, GuideRequest, GuideResponse
from trip.models import Destination, TripRequest, TripResponse
from trip.recommender import recommend

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA = BASE_DIR.parent / "data" / "destinations.json"
DEFAULT_CITIES = BASE_DIR.parent / "data" / "cities.json"
# Toman per US dollar shown as the default in the UI; users should enter today's rate.
DEFAULT_USD_RATE = int(os.environ.get("DEFAULT_USD_RATE", "100000"))


def create_app(data_path: Path | None = None, cities_path: Path | None = None) -> FastAPI:
    destinations = load_destinations(data_path or Path(os.environ.get("DESTINATIONS_JSON", DEFAULT_DATA)))
    cities = load_cities(cities_path or Path(os.environ.get("CITIES_JSON", DEFAULT_CITIES)))
    city_by_id = {c.id: c for c in cities}
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

    @app.get("/api/guide/meta")
    def guide_meta() -> dict:
        return describe_choices()

    @app.get("/api/cities", response_model=list[CitySummary])
    def list_cities() -> list[CitySummary]:
        return [CitySummary(id=c.id, name=c.name, intro=c.intro, categories=c.categories,
                            place_count=len(c.places)) for c in cities]

    @app.get("/api/cities/detect")
    def detect(q: str) -> dict:
        city = detect_city(q[:300], cities)
        return {"city": city.id if city else None}

    @app.post("/api/guide", response_model=GuideResponse)
    def city_guide(req: GuideRequest) -> GuideResponse:
        city = city_by_id.get(req.city)
        if city is None:
            raise HTTPException(404, "city not found")
        return guide(req, city)

    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    return app


app = create_app()
