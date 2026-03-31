"""CLI entry point for the McGill Course Explorer."""

from __future__ import annotations

import argparse
import asyncio
import sys


def cli():
    parser = argparse.ArgumentParser(description="McGill Course Explorer")
    sub = parser.add_subparsers(dest="command")

    # --- serve ---
    serve = sub.add_parser("serve", help="Start the FastAPI server")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")

    # --- scrape ---
    scrape = sub.add_parser("scrape", help="Run the course scraper")
    scrape.add_argument("--faculty", action="append", metavar="NAME")
    scrape.add_argument("--max-course-pages", type=int, default=None)
    scrape.add_argument("--max-program-pages", type=int, default=None)
    scrape.add_argument("--no-headless", action="store_true")

    # --- pipeline ---
    pipeline = sub.add_parser("pipeline", help="Run the full ingest pipeline")
    pipeline.add_argument("--faculty", action="append", metavar="NAME")
    pipeline.add_argument("--dept", action="append", metavar="CODE")
    pipeline.add_argument("--max-course-pages", type=int, default=None)
    pipeline.add_argument("--max-program-pages", type=int, default=None)

    # --- seed ---
    sub.add_parser("seed", help="Load courses.json into databases")

    args = parser.parse_args()

    if args.command == "serve":
        import uvicorn
        uvicorn.run(
            "mcgill.api.app:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    elif args.command == "scrape":
        from mcgill.scraper.catalogue import run as run_scrape
        asyncio.run(run_scrape(
            faculty_filter=args.faculty,
            max_course_pages=args.max_course_pages,
            max_program_pages=args.max_program_pages,
            headless=not args.no_headless,
        ))
    elif args.command == "pipeline":
        from mcgill.pipeline.graph import run_pipeline
        asyncio.run(run_pipeline(
            faculty_filter=args.faculty,
            dept_filter=args.dept,
            max_course_pages=args.max_course_pages,
            max_program_pages=args.max_program_pages,
        ))
    elif args.command == "seed":
        from mcgill.db.migrations import seed_from_json
        asyncio.run(seed_from_json())
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    cli()
