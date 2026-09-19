-- Manual migration - see migrations/knowledge_base.sql for the pattern.
-- The single "would you like the admission procedure?" yes/no step
-- (await_procedure_interest) was replaced with a richer "would you like to
-- know more about this course?" -> topic list -> optional free-typed
-- question flow - see services/eligibility_service.py's
-- _handle_await_learn_more_interest / _handle_await_info_topic /
-- _handle_await_custom_question. Widens eligibility_events.step's CHECK
-- constraint to allow the three new step names those introduce
-- (await_learn_more_interest, await_info_topic, await_custom_question) so
-- a cancel/timeout while a student is in one of them can actually be
-- recorded - _record_eligibility_event is best-effort and swallows a
-- failed write rather than crashing the flow, so without this migration
-- nothing breaks, but those drop-offs silently stop showing up in the
-- "where do students drop off" analytics.
--
-- await_procedure_interest is dropped from the allowed list going forward
-- since the code never inserts it anymore - this doesn't touch historical
-- rows already carrying that value (CHECK constraints only apply to
-- new/updated rows), they're just not revalidated.
--
-- Safe to re-run: DROP CONSTRAINT IF EXISTS makes it idempotent.

ALTER TABLE eligibility_events
    DROP CONSTRAINT IF EXISTS eligibility_events_step_check;
ALTER TABLE eligibility_events
    ADD CONSTRAINT eligibility_events_step_check
    CHECK (step IN ('await_start_confirm', 'await_course', 'await_category', 'await_summary_confirm', 'await_rule', 'await_learn_more_interest', 'await_info_topic', 'await_custom_question', 'await_another_course'));
