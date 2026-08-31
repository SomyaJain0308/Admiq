# Admiq

**AI-powered admissions support for colleges.**

Admiq is a multi-tenant admissions platform that lets colleges automate repetitive student queries over WhatsApp while giving admissions staff the context they need to follow up with high-intent students.

Instead of forcing counsellors to repeatedly answer the same questions about **fees, eligibility, courses, deadlines, hostels, placements, and admissions**, Admiq uses each college's own documents as its knowledge base, answers students through WhatsApp, escalates uncertain questions to staff, and continuously builds a useful profile of every lead.

The goal is simple:

> **Let AI handle repetitive admissions conversations so humans can focus on conversations that actually need humans.**

---

## ✨ What Admiq Does

### 🤖 AI Admissions Assistant

Students can message a college's WhatsApp number and receive answers grounded in the college's official documents.

The assistant:

* Understands whether a message actually requires document retrieval
* Decomposes complex questions into focused searches
* Retrieves relevant information from the college's knowledge base
* Rewrites failed searches when necessary
* Generates grounded responses using Gemini
* Tracks conversation context and previous assistant responses
* Falls back to a secondary model/retry path when generation fails
* Flags questions when retrieval confidence is too low

This means a student can ask something like:

> "What is the BTech fee and do I need to have PCM in class 12?"

and the system can independently retrieve the relevant information from the college's uploaded documents.

---

### 📚 Document-Based RAG

College staff upload admission documents, PDFs, brochures, fee structures, eligibility documents, and other material.

Admiq processes them through a multi-stage ingestion pipeline:

```text
PDF
 │
 ▼
Docling extraction + OCR
 │
 ├── Good extraction ──────────────┐
 │                                 │
 ├── Poor extraction → Full OCR ───┤
 │                                 │
 └── Still poor → EasyOCR/Tesseract
                                   │
                                   ▼
                              Markdown
                                   │
                                   ▼
                         Header-aware chunking
                                   │
                                   ▼
                       Contextual retrieval context
                                   │
                                   ▼
                             Embeddings
                                   │
                                   ▼
                         PostgreSQL + pgvector
```

Each chunk contains both the extracted content and contextual information describing where it belongs in the document.

Embeddings are stored in PostgreSQL using `pgvector` with an HNSW index for efficient similarity search.

---

## 🧠 Retrieval Pipeline

The core assistant is implemented as a **LangGraph state machine**.

```text
                     ┌─────────────────┐
                     │   User Query    │
                     └────────┬────────┘
                              ▼
                     ┌─────────────────┐
                     │ Resolve Query   │
                     └────────┬────────┘
                              │
                 ┌────────────┴────────────┐
                 │                         │
          No retrieval needed        Retrieval needed
                 │                         │
                 │                         ▼
                 │                  ┌─────────────┐
                 │                  │   Retrieve  │
                 │                  └──────┬──────┘
                 │                         │
                 │                  Results found?
                 │                    │         │
                 │                   Yes        No
                 │                    │         │
                 │                    │         ▼
                 │                    │    ┌──────────┐
                 │                    │    │ Re-query │
                 │                    │    └────┬─────┘
                 │                    │         │
                 │                    │    Retry limit?
                 │                    │      │     │
                 │                    │     No    Yes
                 │                    │      │     │
                 │                    │      └──┐  ▼
                 │                    │         │ Flag
                 │                    │         │ low
                 └────────────────────┴─────────┘ confidence
                              │
                              ▼
                       Build System Prompt
                              │
                              ▼
                       Primary LLM Call
                              │
                       ┌──────┴──────┐
                       │             │
                    Success        Failure
                       │             │
                       │             ▼
                       │        Fallback / Retry
                       │             │
                       │             ▼
                       └──────┬──────┘
                              ▼
                         Final Response
```

### Query resolution

Before performing a vector search, the system determines whether retrieval is necessary.

Greetings, thanks, and simple conversational messages can bypass the document lookup entirely.

For complex admissions questions, the resolver can split the message into multiple focused search queries.

### Retrieval

Each sub-query is embedded and searched against the college's vector store.

Results are filtered using a configurable cosine-distance threshold.

### Retrieval retry

If a query produces no sufficiently relevant result, Admiq asks the query model to rewrite it and retries retrieval.

### Human escalation

If retrieval remains unsuccessful after the configured retries, the question enters the **low-confidence queue** for staff review.

Importantly, the student still receives a best-effort response rather than being left hanging.

---

# 👥 Student Intelligence

Admiq isn't just a chatbot.

Every conversation can contribute to a persistent student profile.

When a session closes, a background task analyzes the conversation and updates the student's profile with information such as:

* Course interest
* Academic scores explicitly mentioned by the student
* Current concerns or objections
* Competing colleges
* Parent/guardian involvement
* Reason for conversation drop-off
* Running conversation summary
* Interest signal history

For example, instead of a counsellor seeing:

> **Rahul, 18, BTech enquiry**

they can see useful context such as:

```text
Course interest:
Computer Science Engineering

Academic scores:
Class 12: 91%
JEE Main percentile: 94.2

Open concern:
Feels tuition fees are too high

Competing colleges:
College A
College B

Guardian involvement:
Father is involved in the final decision

Drop-off reason:
Stopped responding after discussing fees
```

The point is to make the eventual human conversation significantly better.

---

# 📈 Lead Scoring

Every student receives a **0–100 lead score**.

The score is deliberately rule-based rather than another LLM call, keeping it inexpensive and deterministic.

The score combines:

| Signal                 |  Weight |
| ---------------------- | ------: |
| Recent interest trend  |      45 |
| Recency of activity    |      35 |
| Conversation frequency |      20 |
| Unresolved concerns    | Penalty |
| Competing colleges     | Penalty |
| Drop-off reason        | Penalty |

The score is recalculated:

* When a session is processed
* During the nightly batch recomputation

This allows inactive leads to naturally become less valuable over time without requiring a new conversation.

Students in the dashboard are sorted by lead score so staff can prioritize follow-ups.

---

# 🔁 Automated Re-engagement

Admiq can identify students who stopped responding and attempt a personalized follow-up.

The re-engagement system considers:

* Student lead score
* Recent interest signals
* Conversation summary
* Course interest
* Open concerns
* College strengths

The generated message can use the college's configured strengths, such as:

* Placement performance
* Tuition fees
* Hostel facilities
* Campus facilities
* Other differentiators

The system deliberately avoids sending nudges to students with negative interest signals or sufficiently low lead scores.

---

# 🧑‍💼 Staff Dashboard

Admiq includes a React-based staff dashboard.

### Dashboard

Provides a quick overview of:

* Low-confidence questions waiting for staff
* Students
* Staff members with college access

### Students

Staff can:

* Search students
* Sort by lead score
* View course interest
* View contact information
* Open a student's full profile
* Read their conversation
* Review AI-generated profile signals

### Student Detail

The student detail view combines:

```text
Student
   │
   ├── Lead score
   ├── Course interest
   ├── Academic scores
   ├── Profile summary
   ├── Open concerns
   ├── Guardian involvement
   ├── Competing colleges
   ├── Drop-off reason
   ├── Internal notes
   │
   └── Conversation history
```

### Low-Confidence Queue

When the assistant isn't confident enough to answer a question, staff can see:

* The student's question
* The assistant's attempted answer
* The unresolved query
* A reply interface

Staff responses can subsequently become temporary retrieval knowledge, allowing the system to benefit from answers that humans have already provided.

### Staff Management

College staff can be:

* Added
* Edited
* Removed
* Searched
* Activated/deactivated

### College Settings

Staff can configure:

* College name
* Phone number
* Email
* Key college strengths

---

# 💬 WhatsApp Integration

Admiq integrates with the **Meta WhatsApp Cloud API**.

The production message flow is:

```text
Student
   │
   ▼
WhatsApp
   │
   ▼
Meta Webhook
   │
   ▼
Admiq Webhook
   │
   ├── Verify webhook
   ├── Validate signature
   ├── Deduplicate message
   ├── Identify college
   ├── Find/create student
   ├── Find/create session
   │
   ▼
LangGraph Agent
   │
   ▼
RAG / LLM
   │
   ▼
Response
   │
   ▼
WhatsApp Cloud API
   │
   ▼
Student
```

Webhook message IDs are stored to protect against duplicate processing when Meta retries webhook deliveries.

There is also a `/test-chat` endpoint that allows the assistant flow to be tested without a real WhatsApp number.

---

# 🏢 Multi-Tenancy

Admiq is designed for multiple colleges from the beginning.

Each college has its own:

* WhatsApp number
* Students
* Staff
* Documents
* Knowledge base
* Conversations
* Low-confidence queue

Tenant isolation is enforced through composite foreign keys and constraints rather than relying solely on developers remembering to add a `college_id` filter everywhere.

Conceptually:

```text
                    Admiq
                      │
          ┌───────────┴───────────┐
          │                       │
       College A               College B
          │                       │
     ┌────┼────┐             ┌────┼────┐
     │    │    │             │    │    │
 Students Docs Staff      Students Docs Staff
     │
 Conversations
     │
 Profiles
```

Staff can also belong to multiple colleges through the `staff_colleges` join table.

---

# 🗃️ Data Model

The main PostgreSQL entities are:

```text
colleges
   │
   ├── whatsapp_numbers
   │
   ├── documents
   │      │
   │      └── chunks
   │
   ├── students
   │      │
   │      └── student_sessions
   │              │
   │              └── messages
   │
   └── staff_colleges
          │
          └── college_staff

low_confidence_queries
   ├── student
   ├── question message
   └── answer message
```

The database uses:

* PostgreSQL
* `pgvector`
* `pg_cron`
* JSONB for flexible profile data
* Composite tenant-aware foreign keys
* HNSW vector indexes

### Automated database jobs

`pg_cron` handles:

* Closing inactive sessions after 30 minutes
* Removing expired staff-answer chunks

Celery handles higher-level application jobs such as profile generation and lead scoring.

---

# ⚙️ Background Processing

Admiq uses **Celery + Redis** for asynchronous workloads.

Current scheduled jobs include:

| Job                       |    Frequency | Purpose                               |
| ------------------------- | -----------: | ------------------------------------- |
| Closed session processing |  Every 5 min | Generate/merge student profiles       |
| Lead score recomputation  |        Daily | Recalculate scores as activity decays |
| Re-engagement check       | Every 10 min | Find eligible inactive leads          |

Document processing is also performed asynchronously so PDF parsing and embedding generation don't block API requests.

---

# 📊 Observability

The application exposes Prometheus metrics covering areas such as:

* API latency
* Agent latency
* LLM input/output tokens
* Retrieval distance
* Retrieved chunks
* Relevant chunks
* Agent errors
* Agent retries
* Document ingestion latency
* OCR method
* Document quality scores
* Celery task outcomes
* Lead score distributions
* Re-engagement outcomes

**LangSmith** tracing is also integrated for LLM/agent observability.

The Docker Compose stack includes:

* Prometheus
* Grafana
* Node Exporter
* Redis Exporter

This makes it possible to monitor both application behavior and infrastructure.

---

# 🧱 Tech Stack

## Backend

* **Python 3.11**
* **FastAPI**
* **SQLAlchemy 2.0**
* **PostgreSQL**
* **pgvector**
* **Celery**
* **Redis**
* **Pydantic**
* **JWT authentication**

## AI / RAG

* **Google Gemini**

  * `gemini-2.5-flash`
  * `gemini-embedding-001`
* **LangChain**
* **LangGraph**
* **LangSmith**
* **Docling**
* **EasyOCR**
* **Tesseract**
* **PyMuPDF**

## Frontend

* **React 19**
* **Vite**
* **React Router**
* **TanStack Query**
* **Tailwind CSS**
* **Radix UI**
* **Lucide React**

## Infrastructure

* **Docker / Docker Compose**
* **Prometheus**
* **Grafana**
* **Redis Exporter**
* **Node Exporter**
* **Supabase**

---

# 🚀 Getting Started

## Prerequisites

You'll need:

* Docker + Docker Compose
* A PostgreSQL database with `pgvector` and `pg_cron`
* Redis
* Google Gemini API key
* Supabase project/storage if using the included storage integration
* Meta WhatsApp Cloud API credentials
* LangSmith credentials if tracing is enabled

---

## 1. Clone the repository

```bash
git clone <repository-url>
cd Admiq-main
```

---

## 2. Configure the backend

Create:

```text
.env
```

in the project root for Docker Compose.

Use `.env.example` as the starting point.

Important configuration includes:

```env
GEMINI_API_KEY=...

LANGCHAIN_TRACING_KEY=true
LANGCHAIN_API_KEY=...
LANGCHAIN_PROJECT=CollegeChatbot

DATABASE_URL=...
REDIS_DATABASE_URL=...

WHATSAPP_VERIFY_TOKEN=...
META_APP_SECRET=...
WHATSAPP_ACCESS_TOKEN=...
```

The backend also supports configuration for:

* LLM models
* Retrieval thresholds
* Retry limits
* Session token budgets
* Logging
* Storage
* JWT authentication
* Internal task authentication

**Never commit real secrets to Git.**

---

## 3. Initialize the database

The database schema is located at:

```text
backend/app/schema.sql
```

It creates:

* Required PostgreSQL extensions
* Application tables
* Constraints
* Vector indexes
* Scheduled `pg_cron` jobs
* The private document storage bucket

Apply the schema to your PostgreSQL/Supabase database before running the application.

---

## 4. Start the backend stack

```bash
docker compose up --build
```

The Compose stack runs:

```text
backend
celery_worker
celery_beat
prometheus
grafana
node-exporter
redis-exporter
```

The API will be available at:

```text
http://localhost:8000
```

FastAPI's interactive API documentation is available through its standard Swagger/ReDoc endpoints.

---

# 🖥️ Running the Frontend

The frontend is a separate Vite application.

```bash
cd frontend
npm install
```

Create:

```text
frontend/.env
```

with:

```env
VITE_API_BASE_URL=http://localhost:8000
```

Start the development server:

```bash
npm run dev
```

Build for production:

```bash
npm run build
```

Run linting:

```bash
npm run lint
```

---

# 🔌 API Surface

The backend exposes routes for:

| Area                                    | Purpose                                    |
| --------------------------------------- | ------------------------------------------ |
| `/api/v1/whatsapp/webhook`              | WhatsApp webhook verification and messages |
| `/api/v1/router/test/chat`              | Test the chatbot without WhatsApp          |
| `/api/v1/router/colleges/...`           | College management                         |
| `/api/v1/router/staff/...`              | Staff management/authentication            |
| `/api/v1/router/students/...`           | Student and conversation data              |
| `/api/v1/router/colleges/.../documents` | Document upload/status                     |
| `/api/v1/router/low_confidence/...`     | Human review queue                         |
| Metrics endpoints                       | Prometheus/application metrics             |
| Health endpoint                         | Service health checks                      |

The exact request/response schemas are defined in:

```text
backend/app/schemas/
```

and the corresponding routers live under:

```text
backend/app/api/v1/routers/
```

---

# 📁 Project Structure

```text
Admiq-main/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   │       └── routers/
│   │   │           ├── colleges.py
│   │   │           ├── documents.py
│   │   │           ├── health_check.py
│   │   │           ├── low_confidence.py
│   │   │           ├── metrics.py
│   │   │           ├── staff.py
│   │   │           ├── students.py
│   │   │           ├── test_chat.py
│   │   │           └── whatsapp_chat.py
│   │   │
│   │   ├── background_tasks/
│   │   │   ├── celery_app.py
│   │   │   ├── celery_tasks.py
│   │   │   ├── lead_scoring_tasks.py
│   │   │   ├── reengagement_tasks.py
│   │   │   └── student_profile_tasks.py
│   │   │
│   │   ├── models/
│   │   ├── monitoring/
│   │   ├── rag/
│   │   │   ├── agent.py
│   │   │   ├── chunking.py
│   │   │   ├── document_processor.py
│   │   │   ├── retrieval.py
│   │   │   ├── reengagement.py
│   │   │   ├── security.py
│   │   │   ├── staff_reply_context.py
│   │   │   └── student_profile.py
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── main.py
│   │   └── schema.sql
│   │
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── context/
│   │   ├── hooks/
│   │   ├── lib/
│   │   └── pages/
│   │       ├── DashboardHome.jsx
│   │       ├── Login.jsx
│   │       ├── LowConfidenceQueue.jsx
│   │       ├── StaffManagement.jsx
│   │       ├── StudentsList.jsx
│   │       ├── StudentDetail.jsx
│   │       └── CollegeSettings.jsx
│   ├── package.json
│   └── vite.config.js
│
├── docker-compose.yml
├── prometheus.yml
├── .env.example
└── README.md
```

---

# 🔐 Security

Admiq includes several security mechanisms:

* JWT-based authentication
* Password hashing with Argon2
* College membership verification
* Tenant-aware database relationships
* WhatsApp webhook verification
* WhatsApp message deduplication
* Rate limiting backed by Redis
* Private document storage
* Server-side Supabase service-role credentials
* Structured request validation through Pydantic

The Supabase service-role key must remain strictly server-side and must never be exposed to the frontend.

---

# 🧪 Testing the Assistant

For development, the project includes a test-chat endpoint so the RAG system can be exercised without configuring a live WhatsApp number.

The intended development flow is:

```text
Upload college documents
        ↓
Wait for document processing
        ↓
Verify chunks/embeddings
        ↓
Send test question
        ↓
Inspect response + sources
        ↓
Test low-confidence behavior
        ↓
Test staff response
        ↓
Verify staff answer becomes retrieval knowledge
```

This is particularly useful for testing the RAG pipeline before connecting Meta's webhook infrastructure.

---

# ⚠️ Current Limitations

Admiq is an active build rather than a finished production SaaS product.

Current known limitations include:

* Automated test coverage is not yet established
* Database schema changes are currently managed through `schema.sql` rather than a fully adopted migration workflow
* CORS is currently configured broadly for development
* Some production infrastructure and deployment configuration still needs hardening
* Grafana dashboards are included in the architecture but still require further dashboard work
* WhatsApp production configuration requires external Meta infrastructure
* LLM model configuration is currently centered around Gemini

These should be addressed before treating the repository as production-hardened.

---

# 🗺️ Roadmap

Potential next steps include:

* [ ] Comprehensive backend test suite
* [ ] Frontend automated tests
* [ ] Production CORS configuration
* [ ] Formal database migration workflow
* [ ] Production Grafana dashboards
* [ ] More granular staff permissions/roles
* [ ] Improved lead analytics
* [ ] Richer admissions funnel analytics
* [ ] More WhatsApp message types
* [ ] Additional LLM providers/fallbacks
* [ ] Production deployment automation
* [ ] Improved document versioning
* [ ] Better evaluation of RAG answer quality
* [ ] Automated retrieval/response evaluation datasets

---

# 🎯 Product Philosophy

Admiq is built around a simple distinction:

### AI handles volume.

Repeated questions, document lookup, basic admissions information, follow-ups, and routine conversations can be automated.

### Humans handle intent.

When a student has serious objections, is comparing colleges, is close to making a decision, or asks something the system cannot confidently answer, staff get the context they need to step in.

The system therefore isn't trying to replace admissions counsellors.

It's trying to make sure **their time is spent where it actually matters.**

---

## License

No open-source license has currently been specified for this repository.

Until a license is added, the default copyright protections apply to the codebase.
