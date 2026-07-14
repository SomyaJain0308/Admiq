DROP TABLE IF EXISTS chunks CASCADE;
DROP TABLE IF EXISTS low_confidence_queries CASCADE;
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS documents CASCADE;
DROP TABLE IF EXISTS whatsapp_numbers CASCADE;
DROP TABLE IF EXISTS students CASCADE;
DROP TABLE IF EXISTS college_staff CASCADE;
DROP TABLE IF EXISTS colleges CASCADE;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_cron;

CREATE TABLE colleges (
    college_id      SERIAL PRIMARY KEY,
    college_name    TEXT NOT NULL,
    college_phone   TEXT NOT NULL,
    college_email   TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE whatsapp_numbers (
    number_id        SERIAL PRIMARY KEY,
    college_id       INT REFERENCES colleges(college_id) ON DELETE CASCADE NOT NULL,
    phone_number_id  TEXT UNIQUE NOT NULL,
    display_number   TEXT,
    verified_at      TIMESTAMP,
    created_at       TIMESTAMP DEFAULT NOW()
);

CREATE TABLE college_staff (
    staff_id        SERIAL PRIMARY KEY,
    college_id      INT REFERENCES colleges(college_id) ON DELETE CASCADE NOT NULL,
    staff_name      TEXT NOT NULL,
    staff_email     TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (college_id, staff_id)
);

CREATE TABLE students (
    student_id       SERIAL PRIMARY KEY,
    college_id       INT REFERENCES colleges(college_id) ON DELETE CASCADE NOT NULL,
    student_phone    TEXT NOT NULL,
    student_name     TEXT,
    course_interest  TEXT,
    academic_scores  JSONB,
    summary          TEXT,
    student_status   TEXT DEFAULT 'new' CHECK (student_status IN ('new', 'contacted', 'interested', 'enrolled', 'not_interested')),
    assigned_to      INT,
    internal_notes   TEXT,
    created_at       TIMESTAMP DEFAULT NOW(),
    UNIQUE (college_id, student_phone),
    UNIQUE (college_id, student_id),
    FOREIGN KEY (college_id, assigned_to) REFERENCES college_staff(college_id, staff_id)
);

CREATE TABLE messages (
    message_id     SERIAL PRIMARY KEY,
    college_id     INT REFERENCES colleges(college_id) ON DELETE CASCADE NOT NULL,
    student_id     INT NOT NULL,
    messager_role  TEXT NOT NULL CHECK (messager_role IN ('student', 'assistant')),
    content        TEXT NOT NULL,
    sources        JSONB,
    feedback       BOOLEAN,
    created_at     TIMESTAMP DEFAULT NOW(),
    UNIQUE (college_id, message_id),
    CHECK (feedback IS NULL OR messager_role = 'assistant'),
    FOREIGN KEY (college_id, student_id) REFERENCES students(college_id, student_id) ON DELETE CASCADE
);

CREATE TABLE documents (
    document_id       SERIAL PRIMARY KEY,
    college_id        INT REFERENCES colleges(college_id) ON DELETE CASCADE NOT NULL,
    file_name         TEXT NOT NULL,
    storage_path      TEXT NOT NULL,
    extraction_method TEXT,
    quality_score     NUMERIC(4,3),
    num_pages         INT,
    document_status   TEXT NOT NULL DEFAULT 'processing' CHECK (document_status IN ('processing', 'success', 'failed')),
    error             TEXT,
    uploaded_by       INT NOT NULL,
    created_at        TIMESTAMP DEFAULT NOW(),
    UNIQUE (college_id, document_id),
    FOREIGN KEY (college_id, uploaded_by) REFERENCES college_staff(college_id, staff_id)
);

CREATE TABLE low_confidence_queries (
    query_id             SERIAL PRIMARY KEY,
    college_id           INT REFERENCES colleges(college_id) ON DELETE CASCADE NOT NULL,
    student_id           INT NOT NULL,
    question_message_id  INT NOT NULL,
    answer_message_id    INT NOT NULL UNIQUE,
    similarity_score     NUMERIC(5,4),
    resolved             BOOLEAN DEFAULT FALSE,
    resolved_by          INT,
    resolved_at          TIMESTAMP,
    flagged_at           TIMESTAMP DEFAULT NOW(),
    UNIQUE (college_id, query_id),
    FOREIGN KEY (college_id, student_id) REFERENCES students(college_id, student_id) ON DELETE CASCADE,
    FOREIGN KEY (college_id, question_message_id) REFERENCES messages(college_id, message_id) ON DELETE CASCADE,
    FOREIGN KEY (college_id, answer_message_id) REFERENCES messages(college_id, message_id) ON DELETE CASCADE,
    FOREIGN KEY (college_id, resolved_by) REFERENCES college_staff(college_id, staff_id)
);

CREATE TABLE chunks (
    chunk_id         SERIAL PRIMARY KEY,
    document_id      INT,
    college_id       INT REFERENCES colleges(college_id) ON DELETE CASCADE NOT NULL,
    chunk_content    TEXT NOT NULL,
    embedding        vector(768) NOT NULL,
    chunk_index      INT NOT NULL,
    source_type      TEXT NOT NULL CHECK (source_type IN ('document', 'staff_answer')),
    source_query_id  INT,
    expires_at       TIMESTAMP DEFAULT NULL,
    CHECK ((source_type = 'document' AND document_id IS NOT NULL) OR (source_type = 'staff_answer' AND source_query_id IS NOT NULL)),
    CHECK (source_type = 'staff_answer' OR expires_at IS NULL),
    FOREIGN KEY (college_id, document_id) REFERENCES documents(college_id, document_id) ON DELETE CASCADE,
    FOREIGN KEY (college_id, source_query_id) REFERENCES low_confidence_queries(college_id, query_id)
);

DO $$
BEGIN
    PERFORM cron.unschedule('delete-expired-staff-answer-chunks');
EXCEPTION WHEN OTHERS THEN
    NULL;
END;
$$;

SELECT cron.schedule(
  'delete-expired-staff-answer-chunks',
  '0 * * * *',
  $$
  DELETE FROM chunks
  WHERE source_type = 'staff_answer'
    AND expires_at IS NOT NULL
    AND expires_at <= NOW();
  $$
);

CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON chunks (college_id);
CREATE INDEX ON chunks (document_id);
CREATE INDEX ON documents (college_id);
CREATE INDEX ON students (college_id);
CREATE INDEX ON students (college_id, student_status);
CREATE INDEX ON messages (student_id, created_at);
CREATE INDEX ON messages (college_id, created_at);
CREATE INDEX ON low_confidence_queries (college_id, resolved);
CREATE INDEX ON low_confidence_queries (student_id);
CREATE INDEX ON whatsapp_numbers (college_id);