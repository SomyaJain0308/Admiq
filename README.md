# Admiq

A multi-tenant WhatsApp chatbot backend for college admissions offices. Students message a college's WhatsApp number and get answers grounded in that college's own documents (brochures, fee structures, eligibility criteria, hostel info, etc.) via RAG, instead of a human having to answer the same 20 questions a hundred times a day. Every conversation also builds up a structured lead profile behind the scenes, so admissions staff aren't starting from zero when they follow up.

This is a backend-first build. There's no frontend yet — right now everything is tested through a `/test-chat` endpoint that mirrors the real WhatsApp flow without needing an actual WhatsApp number.

## Why

Talked to a few people doing admissions outreach and the same complaint kept coming up: staff spend most of their day answering repetitive questions over WhatsApp (fees, deadlines, eligibility) instead of actually talking to the students who are close to deciding. The idea here is to let the bot handle the repetitive stuff, flag anything it can't confidently answer to a human, and quietly build a profile of each lead in the background so staff know exactly who to call and what to say when they do.

## Stack

- **API:** FastAPI (async), Python
- **DB:** PostgreSQL + `pgvector` (hosted on Supabase) via SQLAlchemy 2.0 async ORM
- **Background jobs:** Celery + Redis, with `celery beat` for scheduled tasks
- **LLM / embeddings:** Google Gemini (`gemini-2.5-flash` for chat + extraction, `gemini-embedding-001` for embeddings) via `langchain-google-genai`
- **Agent orchestration:** LangGraph
- **Document parsing:** Docling (PDF → structured markdown) with an OCR fallback chain (Tesseract / EasyOCR) for scanned documents (Only AI generated code in this project.)
- **Observability:** Prometheus metrics + LangSmith tracing (Grafana dashboards planned, see Roadmap)
- **Infra:** Docker Compose (`backend`, `celery_worker`, `celery_beat`, `prometheus`)

## How it works

### 1. A student messages the college's WhatsApp number

Meta sends a webhook to `/api/v1/whatsapp/webhook`. The handler verifies the signature, dedupes on `whatsapp_message_id` (Meta retries webhooks, so this matters), finds-or-creates the student and their active session, and hands the message off to the agent.

### 2. The RAG agent answers it

This is a LangGraph state machine (`rag/agent.py`):

\```
resolve_query → retrieve → re_query (if needed) → flag_low_confidence (if needed) → build_prompt → process → fallback (if needed) → error (if needed)
\```

- **resolve_query** decides if the message even needs a document lookup (skips retrieval for greetings/small talk) and breaks it into 1–4 focused sub-queries if it's a multi-part question.
- **retrieve** embeds each sub-query and does a cosine similarity search against `pgvector`, filtered by a distance threshold.
- **re_query** rewrites and retries sub-queries that came back empty, up to a configured retry limit.
- **flag_low_confidence** — if retries are exhausted and nothing good came back, the query gets queued for human staff review, but the bot still gives its best-effort answer instead of just going silent.
- **process → fallback → error** is the actual generation step: primary model call, with a fallback model and a canned apology as successive safety nets. Every stage logs latency, token usage, and retry counts to Prometheus.

### 3. Documents get ingested through a 3-tier pipeline (Again AI Generated)

Staff upload a PDF, it goes into a Celery task (`document_processor.py`):

1. Try Docling with OCR.
2. If the text quality looks bad (heuristic scoring), retry with Docling forced into full-page OCR mode.
3. If it's still bad, fall back to a manual EasyOCR/Tesseract pass.

Once extracted, the document is chunked (`chunking.py`) using header-aware + recursive splitting, then each chunk gets a short LLM-generated "context" blurb describing where it fits in the document (the Anthropic contextual retrieval technique) before being embedded and stored. Context generation is batched and uses Gemini's context caching to keep it cheap.

### 4. Every session quietly builds a student profile

When a session closes, a Celery task (`student_profile_tasks.py`) summarizes what happened and merges it into the student's long-term profile:

- A running natural-language summary
- Course interest, academic scores explicitly stated by the student
- **Open concerns/objections** — unresolved pushback the student raised (e.g. "thinks fees are too high"), so staff know exactly what to address before they even open the call
- **Competing colleges** the student mentioned considering
- **Parent/guardian involvement** — a short note on who's actually driving the decision
- **Drop-off reason** — if the student went quiet mid-conversation, an inferred reason why

### 5. Leads get scored automatically

A rule-based score (0–100, `services/lead_scoring.py`) — deliberately not another LLM call, this needs to be cheap enough to recompute constantly:

- Recency-weighted trend of the student's interest signal across recent sessions (45 pts)
- How recently they were last active (35 pts, decays to 0 over 30 days of silence)
- How many sessions they've had (20 pts, diminishing returns after ~5)
- Minus penalties for unresolved concerns, competing colleges mentioned, and unresolved drop-offs

Recomputed the moment a session closes, and again every night in a batch job so scores keep decaying for leads who've gone quiet even without a new conversation to trigger it.

## Multi-tenancy

Every college is fully isolated — own WhatsApp number, documents, students, staff. This isn't done with a single global tenant ID; almost every table is keyed on composite `(college_id, ...)` unique constraints and foreign keys instead, so a query can't accidentally leak across colleges just by forgetting a `WHERE` clause on one join. Staff can belong to multiple colleges (`staff_colleges` join table), each student is scoped to one college.

## Data model (high level)

`colleges` → `whatsapp_numbers`, `college_staff` ↔ `staff_colleges` ↔ `colleges`, `students` (with `profile_signals`, `lead_score`, `interest_signal_history` as JSONB/computed fields), `student_sessions` (auto-closed after 30 min idle via `pg_cron`), `messages`, `documents` → `chunks` (pgvector embeddings, HNSW index), `low_confidence_queries` (the human-handoff queue — staff replies here get re-embedded as retrievable, expiring chunks so the bot "learns" the answer for next time).

## Running it

\```bash
docker-compose up
\```

Spins up the FastAPI app, a Celery worker, Celery beat (for the scheduled document-processing / lead-scoring jobs), and Prometheus. Needs a `.env` in `backend/` — see `.env.example` for the required keys (Gemini API key, Supabase/Postgres URL, Redis URL, WhatsApp webhook secrets, LangSmith key).

## Roadmap

Rough order, subject to change:

1. Follow up inside pre determined window.
3. Observability — Grafana dashboards on top of the existing Prometheus metrics
4. Auth — JWT settings already exist in config but nothing's wired up yet; staff/admin endpoints are currently open
5. Frontend — staff dashboard for viewing leads, scores, and the low-confidence review queue
6. Payments - Razorpay

## Known rough edges

Being upfront about this since it's still an active build, not a finished product:

- No auth on staff-facing endpoints yet (see Roadmap #6)
- No formal migration tool — `schema.sql` is the source of truth, but existing databases need manual `ALTER TABLE`s when it changes
- CORS is wide open (`allow_origins=["*"]`) — fine for local dev, not for prod
- No automated test suite yet