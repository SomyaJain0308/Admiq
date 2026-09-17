-- Manual migration (see migrations/knowledge_base.sql for the pattern this
-- follows - schema.sql is the source of truth for fresh installs, this file
-- is what you run by hand against an existing database to bring it up to
-- date). Run once, after knowledge_base.sql, against the same Postgres
-- database schema.sql was applied to.
--
-- What this does:
--   1. Adds UNIQUE (college_id, chunk_id) to chunks, needed so
--      knowledge_conflicts can FK to a chunk scoped by college_id like every
--      other composite FK in this schema (chunk_id alone is already globally
--      unique via its SERIAL PK - this is tenant-scoping belt-and-braces,
--      not a real uniqueness requirement).
--   2. Creates the knowledge_conflicts table - one row per (new chunk,
--      existing chunk) pair that conflict detection (see
--      backend/app/rag/conflict_detection.py) judged to state a different,
--      incompatible fact. Never blocks ingestion; just surfaces the pair for
--      staff to review on the Conflicts page.
--
-- Safe to re-run: every step is idempotent (IF NOT EXISTS / ON CONFLICT-safe
-- constraint add guarded by a existence check).

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        WHERE rel.relname = 'chunks' AND con.contype = 'u'
          AND pg_get_constraintdef(con.oid) = 'UNIQUE (college_id, chunk_id)'
    ) THEN
        ALTER TABLE chunks ADD CONSTRAINT chunks_college_id_chunk_id_key UNIQUE (college_id, chunk_id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS knowledge_conflicts (
    conflict_id          SERIAL PRIMARY KEY,
    college_id            INT REFERENCES colleges(college_id) ON DELETE CASCADE NOT NULL,
    new_chunk_id          INT NOT NULL,
    existing_chunk_id     INT NOT NULL,
    similarity_distance   NUMERIC(5,4),
    explanation           TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'dismissed')),
    resolved_by           INT,
    resolved_at           TIMESTAMP,
    created_at            TIMESTAMP DEFAULT NOW(),

    UNIQUE (college_id, conflict_id),
    UNIQUE (college_id, new_chunk_id, existing_chunk_id),
    FOREIGN KEY (college_id, new_chunk_id) REFERENCES chunks(college_id, chunk_id) ON DELETE CASCADE,
    FOREIGN KEY (college_id, existing_chunk_id) REFERENCES chunks(college_id, chunk_id) ON DELETE CASCADE,
    FOREIGN KEY (college_id, resolved_by) REFERENCES staff_colleges(college_id, staff_id)
);

CREATE INDEX IF NOT EXISTS ix_knowledge_conflicts_college_status_created_at ON knowledge_conflicts (college_id, status, created_at);
CREATE INDEX IF NOT EXISTS ix_knowledge_conflicts_new_chunk_id ON knowledge_conflicts (new_chunk_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_conflicts_existing_chunk_id ON knowledge_conflicts (existing_chunk_id);

COMMIT;
