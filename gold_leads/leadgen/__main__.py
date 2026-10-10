"""CLI:  python -m leadgen check   |   python -m leadgen run [options]   |   python -m leadgen districts"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .agent import Config, LeadAgent


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="leadgen", description="Hashin Gold — Tehran gold shop lead agent")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="find gold shops and update the sheet")
    run.add_argument("--sources", default="google,neshan,mapir,osm", help="comma list of google,neshan,mapir,osm")
    run.add_argument("--sheet-id", help="Google Sheet id (default: $GOOGLE_SHEET_ID)")
    run.add_argument("--service-account", help="service account JSON (default: $GOOGLE_SERVICE_ACCOUNT_FILE)")
    run.add_argument("--enrich", action="store_true", help="research leads on the web with Claude")
    run.add_argument("--enrich-limit", type=int, default=50, help="max leads to research this run")
    run.add_argument("--enrich-refresh", action="store_true", help="ignore cached research")
    run.add_argument("--model", default="claude-opus-5-5", help="Claude model for enrichment")
    run.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    run.add_argument("--workers", type=int, default=4, help="parallel enrichment workers")
    run.add_argument("--grid-step", type=float, default=0.02, help="Neshan grid spacing in degrees (0.02 ≈ 2 km)")
    run.add_argument("--districts-file", type=Path, help="district polygons (.json from `districts` or a .geojson)")
    run.add_argument("--out", type=Path, help="output folder for xlsx/csv")

    sub.add_parser("districts", help="download Tehran district boundaries from OpenStreetMap")
    sub.add_parser("check", help="test every configured API key with one cheap request")

    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.command == "check":
        marks = {True: "OK  ", False: "FAIL", None: "--  "}
        for service, ok, detail in LeadAgent(Config.from_env()).check_keys():
            print(f"[{marks[ok]}] {service}: {detail}")
        return

    if args.command == "districts":
        agent = LeadAgent(Config.from_env())
        print(f"Saved polygons for {agent.download_district_polygons()} districts -> {agent.cfg.districts_file}")
        return

    cfg = Config.from_env(
        sources=[s.strip() for s in args.sources.split(",") if s.strip()],
        sheet_id=args.sheet_id,
        service_account_file=args.service_account,
        enrich=args.enrich,
        enrich_limit=args.enrich_limit,
        enrich_refresh=args.enrich_refresh,
        enrich_model=args.model,
        enrich_effort=args.effort,
        enrich_workers=args.workers,
        grid_step=args.grid_step,
        districts_file=args.districts_file,
        out_dir=args.out,
    )
    print(json.dumps(LeadAgent(cfg).run(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
