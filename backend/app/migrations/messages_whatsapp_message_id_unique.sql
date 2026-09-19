-- Manual migration - see migrations/knowledge_base.sql for the pattern.
-- schema.sql already declares UNIQUE (college_id, whatsapp_message_id) on
-- messages, and services/tenant_service.py's save_inbound_message /
-- api/v1/routers/whatsapp_chat.py's IntegrityError backstop both depend on
-- it actually existing in the database to stop two near-simultaneous
-- webhook deliveries for the same message from both slipping past the
-- SELECT-then-INSERT dedup check and each sending their own reply. Without
-- it, that race has no backstop at all - which is exactly what produced
-- the duplicate "Good news, you meet the eligibility criteria..." message.
--
-- Step 1 deletes any duplicate rows this race has already produced, since
-- ADD CONSTRAINT will fail if any exist. It keeps the earliest row per
-- (college_id, whatsapp_message_id) and drops the rest. NULL
-- whatsapp_message_id values (staff/assistant messages, or any non-
-- WhatsApp channel) are exempt from uniqueness as normal and untouched.
--
-- CAUTION: if a duplicate row being deleted is referenced by
-- low_confidence_queries.question_message_id/answer_message_id, this
-- DELETE will fail on that foreign key. That's intentionally left to
-- surface as an error rather than silently reassigning/dropping a
-- low-confidence-queue entry - check for that first if this step fails:
--   SELECT * FROM low_confidence_queries
--   WHERE question_message_id IN (<ids the DELETE below would remove>)
--      OR answer_message_id IN (<...>);
-- and decide by hand which row to keep in that case.

DELETE FROM messages a
USING messages b
WHERE a.college_id = b.college_id
  AND a.whatsapp_message_id = b.whatsapp_message_id
  AND a.whatsapp_message_id IS NOT NULL
  AND a.message_id > b.message_id;

ALTER TABLE messages
    ADD CONSTRAINT messages_college_id_whatsapp_message_id_key UNIQUE (college_id, whatsapp_message_id);
