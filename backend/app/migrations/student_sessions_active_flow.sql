-- Manual migration - see migrations/knowledge_base.sql for the pattern.
-- schema.sql already defines this column (see student_sessions), but it
-- was apparently never added to the live database, causing:
--   asyncpg.exceptions.UndefinedColumnError: column student_sessions.active_flow does not exist
-- on every webhook call that touches a session (i.e. all of them), via
-- session_service.get_or_create_active_session.
--
-- active_flow holds the eligibility-checker's (or any future guided-flow's)
-- state between messages - see services/eligibility_service.py's module
-- docstring ("Flow state lives in StudentSession.active_flow (JSONB)").
-- NULL means ordinary free-chat with the RAG agent, same as schema.sql's
-- own comment on this column.
--
-- Safe to re-run: IF NOT EXISTS makes it idempotent.

ALTER TABLE student_sessions
    ADD COLUMN IF NOT EXISTS active_flow JSONB;
