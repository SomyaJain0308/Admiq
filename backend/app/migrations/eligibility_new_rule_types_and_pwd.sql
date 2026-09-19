-- Manual migration (see migrations/knowledge_base.sql for the pattern this
-- follows - schema.sql is the source of truth for fresh installs, this file
-- is what you run by hand against an existing database to bring it up to
-- date). Run once against the same Postgres database schema.sql was
-- applied to.
--
-- What this does:
--   1. Widens eligibility_rules.rule_type's CHECK constraint to also allow
--      'best_of_n_subjects', 'domicile_quota', and 'age_limit' - three new
--      rule templates (see schemas/eligibility.py's RULE_CONFIG_MODELS and
--      services/eligibility_service.py) covering criteria the original six
--      types couldn't express: a best-N-of-M-subjects percentage (the way
--      CBSE/most boards actually compute admission percentage), a
--      domicile/state quota, and an age or gap-year cutoff.
--   2. Widens eligibility_events.category's CHECK constraint to also allow
--      'pwd' (Persons with Disabilities), matching the new key added to
--      CATEGORY_LABELS in services/eligibility_service.py - previously PwD
--      applicants had no category of their own and fell back to
--      'general'/'other', losing both their (usually relaxed) cutoff and
--      any per-category analytics visibility.
--
-- Existing rows and configs (including any category_cutoff rule's
-- `thresholds` JSONB, which staff can still leave 'pwd' out of - see
-- find_rule_conflicts' coverage check) are untouched; this only widens what
-- a *new* row is allowed to contain.
--
-- Safe to re-run: DROP CONSTRAINT IF EXISTS makes the whole thing idempotent.

ALTER TABLE eligibility_rules
    DROP CONSTRAINT IF EXISTS eligibility_rules_rule_type_check;
ALTER TABLE eligibility_rules
    ADD CONSTRAINT eligibility_rules_rule_type_check
    CHECK (rule_type IN ('min_percentage', 'min_subject_marks', 'required_stream', 'entrance_cutoff', 'category_cutoff', 'custom_yesno', 'best_of_n_subjects', 'domicile_quota', 'age_limit'));

ALTER TABLE eligibility_events
    DROP CONSTRAINT IF EXISTS eligibility_events_category_check;
ALTER TABLE eligibility_events
    ADD CONSTRAINT eligibility_events_category_check
    CHECK (category IS NULL OR category IN ('general', 'obc', 'sc', 'st', 'ews', 'pwd', 'other'));
