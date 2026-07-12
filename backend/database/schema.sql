DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS documents CASCADE;
DROP TABLE IF EXISTS low_confidence_queries CASCADE;
DROP TABLE IF EXISTS whatsapp_numbers CASCADE;
DROP TABLE IF EXISTS students CASCADE;
DROP TABLE IF EXISTS staff_colleges CASCADE;
DROP TABLE IF EXISTS college_staff CASCADE;
DROP TABLE IF EXISTS colleges CASCADE;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE colleges (
    college_id      SERIAL PRIMARY KEY NOT NULL,
    college_name    TEXT NOT NULL,
    domain_name     TEXT NOT NULL,
    phone           TEXT NOT NULL,
    email           TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE college_staff (
    staff_id        SERIAL PRIMARY KEY NOT NULL,
    name            TEXT NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL
);

CREATE TABLE staff_colleges (
    staff_id    INT REFERENCES college_staff(staff_id) ON DELETE CASCADE,
    college_id  INT REFERENCES colleges(college_id) ON DELETE CASCADE,
    PRIMARY KEY (staff_id, college_id)
    -- Consider adding a `role` column here later (e.g. 'owner' vs 'viewer')
    -- if you want different permission levels per staff-college pairing.
    -- Skipping for now — not needed until you actually have colleges
    -- asking for it.
);

CREATE TABLE students (
    student_id            SERIAL PRIMARY KEY NOT NULL,
    college_id            INT REFERENCES colleges(college_id) ON DELETE CASCADE NOT NULL,
    phone                 TEXT NOT NULL,
    name                  TEXT,
    course_interest       TEXT,
    location              TEXT,
    academic_scores       JSONB,          -- e.g. {"jee_main_percentile": 95.2, "class_12_percentage": 92}
    summary               TEXT,
    intent_tag            TEXT,           -- e.g. 'high_intent', 'browsing', 'price_sensitive' 
    status                TEXT DEFAULT 'new'
                            CHECK (status IN ('new', 'contacted', 'interested', 'enrolled', 'not_interested')),
    assigned_to           TEXT,           -- staff name/email currently following up; plain text until a real staff table exists
    internal_notes        TEXT,           -- manual staff notes, separate from the AI-generated summary above
    message_count         INT DEFAULT 0,
    last_message_at       TIMESTAMP DEFAULT NOW(),   -- last time the STUDENT messaged (bot activity)
    last_contacted_at     TIMESTAMP,                  -- last time STAFF followed up (set manually, nullable)
    created_at            TIMESTAMP DEFAULT NOW(),
    deleted_at            TIMESTAMP,
    UNIQUE (college_id, phone)
);

CREATE TABLE whatsapp_numbers (
    number_id        SERIAL PRIMARY KEY NOT NULL,
    college_id       INT REFERENCES colleges(college_id) ON DELETE CASCADE NOT NULL,
    phone_number_id  TEXT UNIQUE NOT NULL,   -- Meta's ID for this number, present in every webhook payload
    display_number   TEXT,                    -- human-readable, e.g. +91XXXXXXXXXX
    verified_at      TIMESTAMP,
    created_at       TIMESTAMP DEFAULT NOW()
);

CREATE TABLE messages (
    message_id  SERIAL PRIMARY KEY NOT NULL,
    student_id   INT REFERENCES students(student_id) ON DELETE CASCADE NOT NULL,
    role         TEXT NOT NULL CHECK (role IN ('student', 'assistant')),
    content      TEXT NOT NULL,
    feedback     BOOLEAN,     -- NULL = no feedback, TRUE = 👍, FALSE = 👎
    created_at   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE documents (
    id                SERIAL PRIMARY KEY NOT NULL,
    college_id        INT REFERENCES colleges(college_id) ON DELETE CASCADE NOT NULL,
    content           TEXT NOT NULL,
    embedding         HALFVEC(3072),
    source_type       TEXT NOT NULL CHECK (source_type IN ('pdf', 'web')),
    source_name       TEXT NOT NULL,
    upload_session_id TEXT NOT NULL,
    chunk_index       INT NOT NULL,
    created_at        TIMESTAMP DEFAULT NOW()
);

CREATE TABLE low_confidence_queries (
    id                SERIAL PRIMARY KEY NOT NULL,
    college_id        INT REFERENCES colleges(college_id) ON DELETE CASCADE NOT NULL,
    student_id        INT REFERENCES students(student_id) ON DELETE CASCADE NOT NULL,
    query_text        TEXT NOT NULL,
    similarity_score  NUMERIC(5,4) NOT NULL,
    resolved          BOOLEAN DEFAULT FALSE,
    resolved_at       TIMESTAMP,
    asked_at          TIMESTAMP DEFAULT NOW()
);
 
CREATE INDEX ON documents USING hnsw (embedding halfvec_cosine_ops);
CREATE INDEX ON documents (college_id, source_type);
CREATE INDEX ON documents (upload_session_id);
CREATE INDEX ON students (college_id);
CREATE INDEX ON students (college_id, status);
CREATE INDEX ON staff_colleges (college_id);  -- reverse lookup: "which staff can access this college"
CREATE INDEX ON messages (student_id, created_at);
CREATE INDEX ON low_confidence_queries (college_id, resolved);
CREATE INDEX ON low_confidence_queries (student_id);
CREATE INDEX ON whatsapp_numbers (college_id);