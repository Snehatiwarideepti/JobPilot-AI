# JobPilot AI

**Explainable AI Career Matching Agent**  
*Search less. Match smarter.*

JobPilot AI searches live job listings, compares them against a candidate's stored profile, and produces evidence-grounded match analyses (`Job requirement -> Candidate evidence -> Decision`) along with skill-gap analysis from observed job requirements.

---

## Architecture

```text
React + Vite Frontend (Tailwind CSS)
        │
        ▼
FastAPI Backend (/jobs, /profile, /skills, /chat, /search, /evaluation, /health)
        │
        ├──► JobProvider Abstraction ──► JobvettaProvider (https://api.jobvetta.com/v1)
        │
        ├──► Ingestion & Normalization ──► PostgreSQL 16 + pgvector
        │
        ├──► Embedding Service (sentence-transformers/all-MiniLM-L6-v2 or OpenAI)
        │
        ├──► Hybrid Retrieval Engine
        │       ├── Keyword Search (PostgreSQL tsvector / ts_rank_cd)
        │       ├── Semantic Search (pgvector cosine similarity)
        │       ├── Reciprocal Rank Fusion (RRF)
        │       └── Multi-factor Reranking (55% semantic, 20% skill, 15% experience, 10% location)
        │
        ├──► Evidence Engine & Match Analyzer
        │       └── Requirement -> Profile Evidence -> MATCH / PARTIAL / GAP / UNKNOWN
        │
        ├──► Skill-Gap Analyzer (aggregated from retrieved job requirements)
        │
        ├──► Tool-Calling Agent (OpenAI function calling + PostgreSQL conversation memory)
        │
        └──► Retrieval Evaluation Pipeline (Hit@5, Hit@10, MRR)
```

---

## Features

- **Live Job Integration (Jobvetta API)**: Server-side `JobvettaProvider` behind an abstract `JobProvider` interface. Normalizes job listings into a canonical schema without inventing missing fields, respects rate limits, and attributes `Source: Jobvetta`.
- **PostgreSQL + pgvector Cache**: Idempotent job ingestion (`scripts/refresh_live_jobs.py`), deduplication by `(source, source_job_id)`, stale-job marking, and 384-dimensional vector storage.
- **Hybrid Retrieval & Reranking**: Combines PostgreSQL full-text search and `pgvector` cosine similarity via Reciprocal Rank Fusion, then reranks using configurable weights (55% semantic, 20% skill match, 15% experience match, 10% location/workplace compatibility).
- **Evidence Engine**: Evaluates job requirements against candidate skills, projects, work experience, and education. Never hallucinates candidate experience.
- **Resume Extraction**: Supports `.pdf`, `.docx`, and `.txt` uploads; extracts structured fields with uncertainty reporting and requires user confirmation before saving.
- **Skill-Gap Analysis**: Computes skill frequency across retrieved jobs for a target role and identifies gaps observed in real listings.
- **Tool-Calling AI Agent**: Uses OpenAI function calling (`search_live_jobs`, `get_job_details`, `analyze_job_fit`, `get_skill_gaps`, `save_job`, `get_saved_jobs`) with PostgreSQL conversation memory.
- **Evaluation Pipeline**: Benchmarks `keyword`, `semantic`, `hybrid`, and `hybrid_rerank` using `Hit@5`, `Hit@10`, and `MRR`. Only reports metrics computed from real runs.

---

## Tech Stack

- **Backend**: Python, FastAPI, SQLAlchemy (asyncio), Pydantic v2, Alembic, httpx, OpenAI SDK, sentence-transformers
- **Database**: PostgreSQL 16 + `pgvector`
- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, React Router, Lucide Icons
- **Infrastructure**: Docker, Docker Compose, Nginx

---

## Environment Setup

Copy `.env.example` to `.env` and configure your keys:

```bash
cp .env.example .env
```

Required variables:

- `JOBVETTA_API_KEY`: Your Jobvetta API Bearer token (server-side only; never exposed to the frontend).
- `OPENAI_API_KEY`: OpenAI API key for the tool-calling agent, resume extraction, and grounded match explanations.
- `DATABASE_URL` / `DATABASE_SYNC_URL`: PostgreSQL connection strings.

---

## Running with Docker (Recommended)

```bash
docker compose up --build
```

- Frontend: `http://localhost:3000`
- Backend API & Swagger Docs: `http://localhost:8000/docs`
- PostgreSQL + pgvector: `localhost:5432`

---

## Local Development

### 1. Start PostgreSQL with pgvector

```bash
docker compose up -d postgres
```

### 2. Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate | Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Run idempotent live job ingestion:

```bash
python scripts/refresh_live_jobs.py --queries "python developer,machine learning" --limit 20
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

---

## Testing

```bash
cd backend
pytest tests -v
```

---

## Limitations & Data Attribution

- **Live Job Data**: Sourced from the Jobvetta API (`https://api.jobvetta.com/v1`). Free-tier rate limits (~50 requests/UTC day) apply.
- **Ranking Weights**: Default reranking weights (`0.55 / 0.20 / 0.15 / 0.10`) are a configurable system setting, not a scientifically optimal formula or hiring probability.
- **Embeddings**: Local `sentence-transformers/all-MiniLM-L6-v2` is configured by default; install `sentence-transformers` or set `USE_OPENAI_EMBEDDINGS=true` to generate embeddings.
- **Evaluation**: Benchmark metrics are only displayed after seeding queries (`POST /evaluation/seed`) and running the pipeline (`POST /evaluation/run`) against populated jobs.
