import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app import catalog
from app.data import CsvImportError, PublisherStore, parse_csv, to_csv
from app.models import AuditRequest, PlanRequest, PlanResponse, Publisher, SiteAudit
from app.planner import build_plan
from app.site_audit import analyze_site

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = BASE_DIR.parent / "data" / "publishers.csv"
MAX_IMPORT_BYTES = 5 * 1024 * 1024


def create_app(csv_path: Path | None = None) -> FastAPI:
    store = PublisherStore(csv_path or Path(os.environ.get("PUBLISHERS_CSV", DEFAULT_CSV)))
    app = FastAPI(title="لینک‌پلنر - پیشنهاددهنده لینک‌سازی و رپورتاژ")
    app.state.store = store
    app.state.analyzer = analyze_site

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(BASE_DIR / "static" / "index.html")

    @app.get("/api/meta")
    def meta() -> dict:
        return {
            "categories": catalog.CATEGORIES,
            "publisher_types": catalog.PUBLISHER_TYPES,
            "products": catalog.PRODUCTS,
            "link_types": catalog.LINK_TYPES,
            "goals": catalog.GOALS,
            "risks": catalog.RISKS,
        }

    @app.post("/api/plan", response_model=PlanResponse)
    def plan(req: PlanRequest) -> PlanResponse:
        return build_plan(req, store.all())

    @app.post("/api/site/analyze", response_model=SiteAudit)
    async def site_analyze(req: AuditRequest) -> SiteAudit:
        try:
            return await app.state.analyzer(req.site_url, req.target_urls)
        except TimeoutError:
            raise HTTPException(504, "site analysis timed out")

    @app.get("/api/publishers", response_model=list[Publisher])
    def publishers() -> list[Publisher]:
        return store.all()

    @app.get("/api/publishers.csv", response_class=PlainTextResponse)
    def export_publishers() -> PlainTextResponse:
        return PlainTextResponse(
            "﻿" + to_csv(store.all()),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=publishers.csv"},
        )

    @app.post("/api/publishers/import")
    async def import_publishers(request: Request) -> dict:
        body = await request.body()
        if len(body) > MAX_IMPORT_BYTES:
            raise HTTPException(413, "file too large")
        try:
            pubs = parse_csv(body.decode("utf-8"))
        except UnicodeDecodeError:
            raise HTTPException(400, {"errors": ["file must be UTF-8 encoded"]})
        except CsvImportError as exc:
            raise HTTPException(400, {"errors": exc.errors[:50]})
        if not pubs:
            raise HTTPException(400, {"errors": ["no rows found"]})
        store.replace(pubs)
        return {"imported": len(pubs)}

    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    return app


app = create_app()
