# College Admissions WhatsApp RAG SaaS

Colleges upload PDFs and we crawl their website; prospective students ask
questions on WhatsApp and a Gemini-powered RAG bot answers using that
college's data. Every inbound number is captured as a lead.

## Stack
- Backend: Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic, Celery + Redis
- DB: PostgreSQL + pgvector
- Frontend: React (Vite) + Tailwind — admin dashboard only
- LLM: Google Gemini (generation + embeddings)
- Ingestion: PDF upload + Firecrawl (website crawling)
- Channel: WhatsApp Cloud API (direct, no BSP)
- Payments: Razorpay
- Infra: Docker (WSL2), nginx/Traefik, deployed on a VPS

## Structure
- `/backend` — FastAPI app
- `/frontend` — React admin dashboard
- `/infra` — docker-compose, nginx/Traefik configs

## Local setup
1. Copy `.env.example` to `.env` and fill in real values.
2. Backend: `cd backend && source .venv/bin/activate`
3. Frontend: `cd frontend && pnpm install` (once Vite is scaffolded in a later phase)
