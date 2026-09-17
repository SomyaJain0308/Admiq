-- Manual migration (no Alembic in this project - schema.sql is the source
-- of truth for fresh installs, this file is what you run by hand against
-- an existing database to bring it up to date). Run once, in order, against
-- the same Postgres database schema.sql was applied to.
--
-- What this does:
--   1. Adds created_by / created_at / retrieval_count / last_retrieved_at to
--      chunks, so the knowledge-base view can show who added a staff answer,
--      when, and how much it's actually being used.
--   2. Relaxes the chunks_source_reference_check constraint so a
--      source_type='staff_answer' chunk no longer requires a
--      source_query_id - staff can add Q&A pairs proactively, with no
--      flagged low-confidence query behind them at all.
--   3. Backfills created_at/created_by for existing staff_answer chunks
--      from the low_confidence_query they were reconstructed from, where
--      one exists (best-effort; rows with no matching query, or where the
--      query itself has since been deleted, are left with the column
--      defaults - created_at NOW(), created_by NULL).
--
-- Safe to re-run: every step is idempotent (IF NOT EXISTS / dynamic
-- constraint lookup / guarded backfill).

BEGIN;

ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS created_by        INT,
    ADD COLUMN IF NOT EXISTS created_at        TIMESTAMP DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS retrieval_count   INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_retrieved_at TIMESTAMP;

-- schema.sql's original CHECK on chunks didn't name its constraints, so
-- Postgres auto-generated a name we can't just hardcode a DROP for -
-- find it by its definition instead and drop whichever old check enforced
-- "source_type = 'staff_answer' AND source_query_id IS NOT NULL".
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        WHERE rel.relname = 'chunks'
          AND con.contype = 'c'
          AND pg_get_constraintdef(con.oid) LIKE '%source_query_id IS NOT NULL%'
    LOOP
        EXECUTE format('ALTER TABLE chunks DROP CONSTRAINT %I', r.conname);
    END LOOP;
END $$;

ALTER TABLE chunks
    ADD CONSTRAINT chunks_source_reference_check
    CHECK (
        (source_type = 'document' AND document_id IS NOT NULL) OR
        (source_type = 'staff_answer' AND document_id IS NULL)
    );

ALTER TABLE chunks
    ADD CONSTRAINT chunks_created_by_fkey
    FOREIGN KEY (college_id, created_by) REFERENCES staff_colleges(college_id, staff_id);

CREATE INDEX IF NOT EXISTS ix_chunks_college_source_type_created_at
    ON chunks (college_id, source_type, created_at);

-- Backfill: existing staff_answer chunks were all created reactively (this
-- migration is what introduces the proactive path), so their real
-- creation time/author is the flagged query they were reconstructed from -
-- flagged_at is close enough to "when the reply was saved" for this to be
-- useful, and resolved_by is exactly who wrote it.
UPDATE chunks c
SET created_at = q.resolved_at,
    created_by = q.resolved_by
FROM low_confidence_queries q
WHERE c.college_id = q.college_id
  AND c.source_query_id = q.query_id
  AND c.source_type = 'staff_answer'
  AND q.resolved_at IS NOT NULL;

COMMIT;
