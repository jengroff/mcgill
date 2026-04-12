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

    # --- scrape (hidden, kept for backwards compat) ---
    scrape = sub.add_parser("scrape", help=argparse.SUPPRESS)
    scrape.add_argument("--faculty", action="append", metavar="NAME")
    scrape.add_argument("--max-course-pages", type=int, default=None)
    scrape.add_argument("--max-program-pages", type=int, default=None)
    scrape.add_argument("--no-headless", action="store_true")

    # --- pipeline ---
    pipeline = sub.add_parser(
        "pipeline",
        help="Run the full ingest pipeline (faculty/dept data, or --general for university-wide)",
    )
    pipeline.add_argument("--faculty", action="append", metavar="NAME")
    pipeline.add_argument("--dept", action="append", metavar="CODE")
    pipeline.add_argument("--max-course-pages", type=int, default=None)
    pipeline.add_argument("--max-program-pages", type=int, default=None)
    pipeline.add_argument(
        "--force",
        action="store_true",
        help="Re-process departments even if already pipelined",
    )
    pipeline.add_argument(
        "--general",
        action="store_true",
        help="Ingest university-wide data (important dates, academic calendar, exams, fees)",
    )

    # --- scrape-general (hidden alias for pipeline --general) ---
    sub.add_parser("scrape-general", help=argparse.SUPPRESS)

    # --- seed (hidden, kept for backwards compat) ---
    sub.add_parser("seed", help=argparse.SUPPRESS)

    # --- ingest-pdf ---
    ingest_pdf = sub.add_parser(
        "ingest-pdf", help="Ingest a PDF file into program page store"
    )
    ingest_pdf.add_argument("file", help="Path to PDF file")
    ingest_pdf.add_argument(
        "--faculty", default="", metavar="SLUG", help="Faculty slug"
    )

    # --- curriculum ---
    curriculum = sub.add_parser("curriculum", help="Generate curriculum recommendation")
    curriculum.add_argument(
        "--interests", nargs="+", required=True, help="Student interests"
    )
    curriculum.add_argument("--program", default="", help="Program slug")
    curriculum.add_argument(
        "--completed", nargs="*", default=[], help="Completed course codes"
    )

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

        asyncio.run(
            run_scrape(
                faculty_filter=args.faculty,
                max_course_pages=args.max_course_pages,
                max_program_pages=args.max_program_pages,
                headless=not args.no_headless,
            )
        )
    elif args.command in ("pipeline", "scrape-general"):
        import logging

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(name)s %(levelname)s %(message)s",
        )

        is_general = args.command == "scrape-general" or getattr(args, "general", False)

        if is_general:
            from backend.db.postgres import init_db, close_db
            from backend.services.scraping.important_dates import scrape_important_dates

            async def _run_general():
                await init_db()

                # Important dates (interactive Drupal form scrape → structured table)
                count = await scrape_important_dates()
                print(f"Important dates: {count} entries stored")

                # General info pages (academic calendar, enrollment, exams, etc.)
                from backend.db.postgres import get_pool
                from backend.services.scraping.faculties import GENERAL_INFO_PAGES
                from backend.services.scraping.browser import (
                    browser_context,
                    fetch_page,
                )
                from backend.services.scraping.parser import parse_program_page
                from urllib.parse import urlparse

                pool = await get_pool()
                pages_stored = 0
                async with browser_context() as ctx:
                    page = await ctx.new_page()
                    for category, urls in GENERAL_INFO_PAGES.items():
                        for url in urls:
                            html = await fetch_page(page, url)
                            if html:
                                pg_title, pg_content = parse_program_page(html)
                                if pg_content:
                                    url_path = urlparse(url).path
                                    async with pool.acquire() as conn:
                                        await conn.execute(
                                            """INSERT INTO program_pages (faculty_slug, path, title, content)
                                               VALUES ($1, $2, $3, $4)
                                               ON CONFLICT (path) DO UPDATE SET
                                                   title = EXCLUDED.title,
                                                   content = EXCLUDED.content,
                                                   scraped_at = now()""",
                                            "university",
                                            url_path,
                                            pg_title,
                                            pg_content,
                                        )
                                    pages_stored += 1
                                    print(f"  {category}: {pg_title or url_path}")

                print(f"General info pages: {pages_stored} stored")

                # Chunk and embed the general info program pages
                from backend.services.embedding.chunker import (
                    chunk_program_page as chunk_pp,
                )
                from backend.services.embedding.voyage import embed_texts
                from backend.services.embedding.vector_store import (
                    insert_program_chunks,
                    create_ivfflat_index,
                )

                async with pool.acquire() as conn:
                    prog_rows = await conn.fetch(
                        "SELECT id, title, content, faculty_slug FROM program_pages WHERE faculty_slug = 'university'"
                    )

                prog_texts: list[str] = []
                prog_meta: list[tuple[int, int]] = []

                for r in prog_rows:
                    chunks = chunk_pp(
                        title=r["title"] or "",
                        content=r["content"] or "",
                        faculty_slug=r["faculty_slug"] or "",
                    )
                    if chunks:
                        prog_meta.append((r["id"], len(prog_texts)))
                        prog_texts.extend(chunks)

                total_chunks = 0
                if prog_texts:
                    prog_embeddings = embed_texts(prog_texts)
                    for i, (page_id, start_idx) in enumerate(prog_meta):
                        end_idx = (
                            prog_meta[i + 1][1]
                            if i + 1 < len(prog_meta)
                            else len(prog_texts)
                        )
                        page_chunks = prog_texts[start_idx:end_idx]
                        page_embs = prog_embeddings[start_idx:end_idx]
                        total_chunks += await insert_program_chunks(
                            page_id, page_chunks, page_embs
                        )

                    await create_ivfflat_index()

                print(f"Embedded {total_chunks} chunks from general info pages")
                await close_db()

            asyncio.run(_run_general())
        else:
            from backend.workflows.ingest.graph import run_pipeline

            asyncio.run(
                run_pipeline(
                    faculty_filter=args.faculty,
                    dept_filter=args.dept,
                    max_course_pages=args.max_course_pages,
                    max_program_pages=args.max_program_pages,
                    force=args.force,
                )
            )
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
