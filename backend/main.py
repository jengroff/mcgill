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

    # --- ingest-pdf ---
    ingest_pdf = sub.add_parser("ingest-pdf", help="Ingest a PDF file into program page store")
    ingest_pdf.add_argument("file", help="Path to PDF file")
    ingest_pdf.add_argument("--faculty", default="", metavar="SLUG", help="Faculty slug")

    # --- curriculum ---
    curriculum = sub.add_parser("curriculum", help="Generate curriculum recommendation")
    curriculum.add_argument("--interests", nargs="+", required=True, help="Student interests")
    curriculum.add_argument("--program", default="", help="Program slug")
    curriculum.add_argument("--completed", nargs="*", default=[], help="Completed course codes")

    args = parser.parse_args()

    if args.command == "serve":
        import uvicorn
        uvicorn.run(
            "backend.api.app:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    elif args.command == "scrape":
        from backend.services.scraping.catalogue import run as run_scrape
        asyncio.run(run_scrape(
            faculty_filter=args.faculty,
            max_course_pages=args.max_course_pages,
            max_program_pages=args.max_program_pages,
            headless=not args.no_headless,
        ))
    elif args.command == "pipeline":
        from backend.workflows.ingest.graph import run_pipeline
        asyncio.run(run_pipeline(
            faculty_filter=args.faculty,
            dept_filter=args.dept,
            max_course_pages=args.max_course_pages,
            max_program_pages=args.max_program_pages,
        ))
    elif args.command == "seed":
        from backend.db.migrations import seed_from_json
        asyncio.run(seed_from_json())
    elif args.command == "ingest-pdf":
        from pathlib import Path
        from backend.workflows.ingestion.graph import IngestionOrchestrator
        from backend.db.postgres import init_db, close_db

        async def _ingest():
            await init_db()
            pdf_bytes = Path(args.file).read_bytes()
            orch = IngestionOrchestrator()
            result = await orch.run(
                source_type="pdf",
                source_path=args.file,
                source_bytes=pdf_bytes,
                faculty_slug=args.faculty,
            )
            await close_db()
            print(f"Chunks stored: {result.get('chunks_stored', 0)}")
            if result.get("errors"):
                for e in result["errors"]:
                    print(f"  Error: {e[:200]}")

        asyncio.run(_ingest())
    elif args.command == "curriculum":
        from backend.workflows.synthesis.curriculum_graph import CurriculumOrchestrator
        from backend.db.postgres import init_db, close_db
        from backend.db.neo4j import init_neo4j, close_neo4j

        async def _curriculum():
            await init_db()
            await init_neo4j()
            orch = CurriculumOrchestrator()
            result = await orch.run(
                student_interests=args.interests,
                program_slug=args.program,
                completed_codes=args.completed,
            )
            await close_db()
            await close_neo4j()
            print(result.get("recommendation", "No recommendation generated."))
            if result.get("errors"):
                for e in result["errors"]:
                    print(f"  Error: {e[:200]}")

        asyncio.run(_curriculum())
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    cli()
