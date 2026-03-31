"""pgvector storage for course chunk embeddings."""

from __future__ import annotations

from mcgill.db.postgres import get_pool


async def insert_chunks(
    course_id: int,
    chunks: list[str],
    embeddings: list[list[float]],
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Clear existing chunks for this course
        await conn.execute(
            "DELETE FROM course_chunks WHERE course_id = $1", course_id
        )

        for i, (text, emb) in enumerate(zip(chunks, embeddings)):
            emb_str = "[" + ",".join(str(v) for v in emb) + "]"
            await conn.execute(
                """INSERT INTO course_chunks (course_id, chunk_index, text, embedding)
                   VALUES ($1, $2, $3, $4::vector)""",
                course_id, i, text, emb_str,
            )
    return len(chunks)


async def search_similar(
    query_embedding: list[float],
    top_k: int = 10,
) -> list[dict]:
    pool = await get_pool()
    emb_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT cc.text, cc.course_id, c.code, c.title,
                      1 - (cc.embedding <=> $1::vector) AS similarity
               FROM course_chunks cc
               JOIN courses c ON c.id = cc.course_id
               ORDER BY cc.embedding <=> $1::vector
               LIMIT $2""",
            emb_str, top_k,
        )
        return [dict(r) for r in rows]


async def insert_program_chunks(
    program_page_id: int,
    chunks: list[str],
    embeddings: list[list[float]],
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM program_chunks WHERE program_page_id = $1", program_page_id
        )
        for i, (text, emb) in enumerate(zip(chunks, embeddings)):
            emb_str = "[" + ",".join(str(v) for v in emb) + "]"
            await conn.execute(
                """INSERT INTO program_chunks (program_page_id, chunk_index, text, embedding)
                   VALUES ($1, $2, $3, $4::vector)""",
                program_page_id, i, text, emb_str,
            )
    return len(chunks)


async def search_similar_programs(
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict]:
    pool = await get_pool()
    emb_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT pc.text, pc.program_page_id, pp.title, pp.faculty_slug,
                      1 - (pc.embedding <=> $1::vector) AS similarity
               FROM program_chunks pc
               JOIN program_pages pp ON pp.id = pc.program_page_id
               ORDER BY pc.embedding <=> $1::vector
               LIMIT $2""",
            emb_str, top_k,
        )
        return [dict(r) for r in rows]


async def create_ivfflat_index() -> None:
    """Create IVFFlat indexes after bulk insert. ~sqrt(N) lists."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Course chunks index
        exists = await conn.fetchval(
            """SELECT EXISTS(
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'idx_chunks_embedding_ivfflat'
            )"""
        )
        if not exists:
            count = await conn.fetchval("SELECT count(*) FROM course_chunks")
            if count > 0:
                lists = max(1, int(count ** 0.5))
                await conn.execute(
                    f"""CREATE INDEX idx_chunks_embedding_ivfflat
                        ON course_chunks USING ivfflat (embedding vector_cosine_ops)
                        WITH (lists = {lists})"""
                )

        # Program chunks index
        exists = await conn.fetchval(
            """SELECT EXISTS(
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'idx_program_chunks_embedding_ivfflat'
            )"""
        )
        if not exists:
            count = await conn.fetchval("SELECT count(*) FROM program_chunks")
            if count > 0:
                lists = max(1, int(count ** 0.5))
                await conn.execute(
                    f"""CREATE INDEX idx_program_chunks_embedding_ivfflat
                        ON program_chunks USING ivfflat (embedding vector_cosine_ops)
                        WITH (lists = {lists})"""
                )
