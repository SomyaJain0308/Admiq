-- Adds eligibility_events: one row per exit from the WhatsApp eligibility-
-- checker flow (a rule verdict - passed/failed/borderline - or a drop-off -
-- cancelled/timed_out), written by services/eligibility_service.py's
-- _record_eligibility_event. Backs the admin-analytics endpoint at
-- GET /router/colleges/{college_id}/eligibility-analytics (pass/fail rate
-- per course, and where students actually drop off). Purely additive - a
-- new table plus a matching entry in models/__init__.py - no changes to any
-- existing table, so this is safe to run against an existing DB with the
-- app still deployed on the old code in the moment before it's rolled out.
--
-- This repo has no migration runner (see schema.sql, applied directly on
-- fresh installs) - run this by hand against any already-provisioned DB:
--   psql "$DATABASE_URL" -f backend/app/db_migrations/0002_add_eligibility_events.sql

CREATE TABLE IF NOT EXISTS eligibility_events (
    event_id      SERIAL PRIMARY KEY,
    college_id    INT NOT NULL,
    student_id    INT NOT NULL,
    course_id     INT,
    -- Every step name eligibility_service.py's state machine uses - see
    -- that file's module docstring.
    step          TEXT NOT NULL CHECK (step IN ('await_start_confirm', 'await_course', 'await_category', 'await_summary_confirm', 'await_rule', 'await_procedure_interest', 'await_another_course')),
    -- The rule's 0-based position in its course's ordered list *at event
    -- time* (same numbering "Question X of Y" shows a student) - not a
    -- foreign key to eligibility_rules, so a later reorder/edit/delete of
    -- that rule doesn't retroactively corrupt historical events. NULL for
    -- any step other than await_rule.
    rule_index    INT,
    outcome       TEXT NOT NULL CHECK (outcome IN ('passed', 'failed', 'borderline', 'cancelled', 'timed_out')),
    created_at    TIMESTAMP DEFAULT NOW(),

    FOREIGN KEY (college_id, student_id) REFERENCES students(college_id, student_id) ON DELETE CASCADE,
    FOREIGN KEY (college_id, course_id) REFERENCES courses(college_id, course_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_eligibility_events_college_id_course_id ON eligibility_events (college_id, course_id);
CREATE INDEX IF NOT EXISTS ix_eligibility_events_college_id_outcome ON eligibility_events (college_id, outcome);
CREATE INDEX IF NOT EXISTS ix_eligibility_events_college_id_created_at ON eligibility_events (college_id, created_at);
