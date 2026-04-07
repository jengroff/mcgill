"""PostgreSQL + pgvector connection pool and table DDL."""

from __future__ import annotations

import asyncpg

from backend.config import settings

_pool: asyncpg.Pool | None = None

DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS faculties (
    id    SERIAL PRIMARY KEY,
    name  VARCHAR(128) UNIQUE NOT NULL,
    slug  VARCHAR(64) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS departments (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(6) UNIQUE NOT NULL,
    faculty_id  INTEGER REFERENCES faculties(id),
    name        VARCHAR(128),
    website     VARCHAR(256)
);

CREATE TABLE IF NOT EXISTS courses (
    id                SERIAL PRIMARY KEY,
    code              VARCHAR(12) UNIQUE NOT NULL,
    slug              VARCHAR(32) UNIQUE NOT NULL,
    title             VARCHAR(256) NOT NULL,
    dept              VARCHAR(6) NOT NULL,
    number            VARCHAR(8) NOT NULL,
    credits           REAL,
    faculty           VARCHAR(128),
    terms             TEXT[] DEFAULT '{}',
    description       TEXT DEFAULT '',
    prerequisites_raw TEXT DEFAULT '',
    restrictions_raw  TEXT DEFAULT '',
    notes_raw         TEXT DEFAULT '',
    url               VARCHAR(512),
    name_variants     TEXT[] DEFAULT '{}',
    scraped_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_courses_dept ON courses(dept);
CREATE INDEX IF NOT EXISTS idx_courses_faculty ON courses(faculty);

CREATE TABLE IF NOT EXISTS course_faculties (
    course_id   INTEGER REFERENCES courses(id) ON DELETE CASCADE,
    faculty_id  INTEGER REFERENCES faculties(id) ON DELETE CASCADE,
    PRIMARY KEY (course_id, faculty_id)
);

CREATE TABLE IF NOT EXISTS course_chunks (
    id          SERIAL PRIMARY KEY,
    course_id   INTEGER REFERENCES courses(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text        TEXT NOT NULL,
    embedding   vector(1024),
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chunks_course ON course_chunks(course_id);

CREATE TABLE IF NOT EXISTS program_pages (
    id            SERIAL PRIMARY KEY,
    faculty_slug  VARCHAR(64) NOT NULL,
    path          VARCHAR(512) UNIQUE NOT NULL,
    title         VARCHAR(256) DEFAULT '',
    content       TEXT DEFAULT '',
    scraped_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_program_pages_faculty ON program_pages(faculty_slug);

CREATE TABLE IF NOT EXISTS program_chunks (
    id              SERIAL PRIMARY KEY,
    program_page_id INTEGER REFERENCES program_pages(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    text            TEXT NOT NULL,
    embedding       vector(1024),
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_program_chunks_page ON program_chunks(program_page_id);

ALTER TABLE departments ADD COLUMN IF NOT EXISTS website VARCHAR(256);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id           SERIAL PRIMARY KEY,
    run_id       UUID UNIQUE NOT NULL,
    status       VARCHAR(20) DEFAULT 'pending',
    phase        VARCHAR(32),
    config       JSONB DEFAULT '{}',
    result       JSONB DEFAULT '{}',
    started_at   TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- Full-text search on courses
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'courses' AND column_name = 'tsv'
    ) THEN
        ALTER TABLE courses ADD COLUMN tsv tsvector
            GENERATED ALWAYS AS (
                to_tsvector('english',
                    coalesce(title, '') || ' ' ||
                    coalesce(description, '') || ' ' ||
                    coalesce(code, ''))
            ) STORED;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_courses_tsv ON courses USING GIN(tsv);

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name          VARCHAR(128) NOT NULL DEFAULT '',
    created_at    TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(128) NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS conversations (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID UNIQUE NOT NULL,
    title      VARCHAR(256) DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);

CREATE TABLE IF NOT EXISTS messages (
    id              SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(16) NOT NULL,
    content         TEXT NOT NULL,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);

-- Curriculum plans
CREATE TABLE IF NOT EXISTS plans (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE,
    title           VARCHAR(256) NOT NULL DEFAULT 'Untitled Plan',
    program_slug    VARCHAR(128),
    status          VARCHAR(16) NOT NULL DEFAULT 'draft',
    target_semesters INTEGER DEFAULT 4,
    student_interests TEXT[] DEFAULT '{}',
    completed_codes TEXT[] DEFAULT '{}',
    plan_markdown   TEXT DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_plans_user ON plans(user_id);

CREATE TABLE IF NOT EXISTS plan_semesters (
    id          SERIAL PRIMARY KEY,
    plan_id     INTEGER REFERENCES plans(id) ON DELETE CASCADE,
    term        VARCHAR(32) NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    courses     TEXT[] DEFAULT '{}',
    total_credits REAL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_plan_semesters_plan ON plan_semesters(plan_id);

CREATE TABLE IF NOT EXISTS plan_documents (
    id              SERIAL PRIMARY KEY,
    plan_id         INTEGER REFERENCES plans(id) ON DELETE CASCADE,
    filename        VARCHAR(256) NOT NULL,
    content_type    VARCHAR(128) DEFAULT '',
    raw_bytes       BYTEA,
    extracted_text  TEXT DEFAULT '',
    uploaded_at     TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_plan_documents_plan ON plan_documents(plan_id);

CREATE TABLE IF NOT EXISTS plan_conversations (
    plan_id         INTEGER REFERENCES plans(id) ON DELETE CASCADE,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
    linked_at       TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (plan_id, conversation_id)
);
"""


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=2,
            max_size=10,
        )
    return _pool


async def init_db() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(DDL)


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
