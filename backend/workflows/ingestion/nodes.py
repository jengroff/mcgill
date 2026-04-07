from __future__ import annotations

import traceback

from backend.workflows.ingestion.state import IngestionState


async def extract_node(state: IngestionState) -> IngestionState:
    """Extract structured text from PDF or URL."""
    try:
        source_type = state.get("source_type", "pdf")

        if source_type == "pdf":
            from backend.services.pdf.extractor import PDFExtractor

            extractor = PDFExtractor()
            result = extractor.extract_structured(state["source_bytes"])
            return {
                "raw_text": extractor.extract_text(state["source_bytes"]),
                "structured_sections": result["sections"],
            }
        elif source_type in ("url", "html"):
            from backend.services.scraping.browser import browser_context, fetch_page

            async with browser_context() as ctx:
                page = await ctx.new_page()
                html = await fetch_page(page, state["source_path"])
            if html:
                from backend.services.scraping.parser import parse_program_page

                title, content = parse_program_page(html)
                return {
                    "raw_text": content,
                    "structured_sections": [{"heading": title, "text": content}],
                }
            return {
                "raw_text": "",
                "structured_sections": [],
                "errors": ["Failed to fetch URL"],
            }
        else:
            return {"errors": [f"Unknown source_type: {source_type}"]}
    except Exception as e:
        return {"errors": [f"extract: {e}\n{traceback.format_exc()}"]}


async def chunk_node(state: IngestionState) -> IngestionState:
    """Chunk extracted sections."""
    try:
        from backend.services.embedding.chunker import chunk_program_page

        all_chunks: list[str] = []
        for section in state.get("structured_sections", []):
            chunks = chunk_program_page(
                title=section.get("heading", ""),
                content=section.get("text", ""),
                faculty_slug=state.get("faculty_slug", ""),
            )
            all_chunks.extend(chunks)

        return {"chunks": all_chunks}
    except Exception as e:
        return {"chunks": [], "errors": [f"chunk: {e}\n{traceback.format_exc()}"]}


async def embed_node(state: IngestionState) -> IngestionState:
    """Generate embeddings for chunks."""
    try:
        from backend.services.embedding.voyage import embed_texts

        chunks = state.get("chunks", [])
        if not chunks:
            return {"embeddings": []}

        embeddings = embed_texts(chunks)
        return {"embeddings": embeddings}
    except Exception as e:
        return {"embeddings": [], "errors": [f"embed: {e}\n{traceback.format_exc()}"]}


async def store_node(state: IngestionState) -> IngestionState:
    """Store embedded chunks in pgvector."""
    try:
        from backend.db.postgres import get_pool
        from backend.services.embedding.vector_store import insert_program_chunks

        chunks = state.get("chunks", [])
        embeddings = state.get("embeddings", [])
        if not chunks or not embeddings:
            return {"chunks_stored": 0, "status": "complete"}

        # Insert as a program page, creating the page record first
        pool = await get_pool()
        async with pool.acquire() as conn:
            page_id = await conn.fetchval(
                """INSERT INTO program_pages (faculty_slug, path, title, content)
                   VALUES ($1, $2, $3, $4)
                   ON CONFLICT (path) DO UPDATE SET content = EXCLUDED.content, scraped_at = now()
                   RETURNING id""",
                state.get("faculty_slug", ""),
                state.get("source_path", f"upload/{state.get('run_id', 'unknown')}"),
                state.get("structured_sections", [{}])[0].get(
                    "heading", "Uploaded PDF"
                ),
                state.get("raw_text", ""),
            )

        count = await insert_program_chunks(page_id, chunks, embeddings)
        return {"chunks_stored": count, "status": "complete"}
    except Exception as e:
        return {
            "chunks_stored": 0,
            "status": "error",
            "errors": [f"store: {e}\n{traceback.format_exc()}"],
        }
