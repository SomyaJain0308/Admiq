-- Adds course hierarchy support (programme type -> branch, e.g. "B.Tech" ->
-- "Computer Science") so a college can offer more than 10 courses without
-- hitting WhatsApp's 10-row list cap. Safe to run against an existing DB:
-- purely additive, nullable column, no data migration needed - every
-- existing course simply has parent_course_id = NULL, which is exactly the
-- flat behavior that already existed.
--
-- This repo has no migration runner (see schema.sql, applied directly on
-- fresh installs) - run this by hand against any already-provisioned DB:
--   psql "$DATABASE_URL" -f backend/app/db_migrations/0001_add_course_parent_course_id.sql

ALTER TABLE courses
    ADD COLUMN IF NOT EXISTS parent_course_id INT REFERENCES courses(course_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS courses_parent_course_id_idx ON courses (parent_course_id);
