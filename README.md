# Airflow Sales

**Agentic sales intelligence that turns a company domain into evidence-backed research, qualification, outreach and an auditable workflow run.**

> The name refers to *deal flow*, not [Apache Airflow](https://airflow.apache.org/) — no DAG engine is involved.

Airflow Sales is a full-stack portfolio project built to demonstrate production-minded agentic application engineering rather than a one-prompt LLM demo. A campaign defines an ICP and qualification criteria. Given a company domain, the system searches the live web, persists source evidence, synthesizes company intelligence, scores the prospect, drafts outreach, critiques unsupported claims, **revises the draft when the critic rejects it (bounded),** records workflow telemetry, and routes approved work through a human decision.

## Product flow

`Campaign → Discover company → Tavily research → Evidence → Research agent → Qualification → Outreach → Critic ⇄ bounded revision → Human approval`

The operator UI is a Next.js workspace with five surfaces — Prospects, Campaigns, Discover, Workflow runs and Analytics — plus a periodic API health indicator (30-second poll), light/dark themes and keyboard-navigable list views. PostgreSQL is the system of record; workflow state is persisted rather than kept only in model context.

## Stack

- **Frontend:** Next.js 16, React 19, TypeScript
- **Backend:** FastAPI, Pydantic, SQLAlchemy 2.x, Alembic (Python 3.11)
- **Data:** PostgreSQL 16
- **AI & tools:** Groq (structured LLM output), Tavily Search
- **Quality:** pytest with deterministic provider fakes, ruff lint/format, TypeScript type checking, production Next build, GitHub Actions (with a Postgres service container)
- **Deployment:** Docker / Docker Compose

## What is real

- Live company research uses Tavily when configured; without keys the API fails cleanly instead of returning mock data.
- LLM research, qualification, outreach, critique **and critic-driven draft revision** use Groq when configured. Every prompt sent is persisted on the workflow event so decisions are reproducible.
- The critic is a real gate: unsupported claims trigger a bounded revision loop (`OUTREACH_MAX_REVISIONS`, default 2), every attempt is recorded, and the final review decides whether a GO prospect waits for human approval. Critic output is coerced defensively — a string `"false"` from the model cannot flip the gate.
- Evidence, prospects, qualifications, workflow runs and workflow events persist in PostgreSQL, with indexes on every foreign key and list-ordering column.
- Workflow events record tool/agent stages, latency, token usage and an **estimated** token cost (usage × configurable per-million pricing — never invented).
- Provider retries and failures are persisted as workflow events; the backend logs failures with step context.
- The dashboard reads the real API; it does not use mock prospect or analytics data. Run success rates are computed from explicit run statuses.
- Company icons are resolved from the company domain with a graceful fallback.

## Local setup

### Prerequisites

Python 3.11, Node 22, Docker (for Postgres).

### 1. Database

```bash
docker compose up -d db
```

### 2. Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # includes pytest + ruff
cp .env.example .env
```

Set `TAVILY_API_KEY`, `GROQ_API_KEY` and (if not using the compose Postgres) your PostgreSQL settings in `.env`. Never commit `.env`.

Run migrations and the API:

```bash
alembic upgrade head
python -m uvicorn backend.app.main:app --reload --port 8000
```

API docs: `http://localhost:8000/docs`

### 3. Frontend

```bash
cd frontend
npm ci
cp .env.local.example .env.local
npm run dev
```

Open `http://localhost:3000`. The default API URL is `http://localhost:8000`.

### Docker option

Create `.env` first (the compose file reads it), then:

```bash
docker compose up --build
```

The api service runs `alembic upgrade head` on boot. The frontend image bakes `NEXT_PUBLIC_API_URL` at build time — pass `--build-arg NEXT_PUBLIC_API_URL=http://<host>:8000` when the API is not on the same host.

### Vercel (backend)

The FastAPI backend deploys as a Vercel Python serverless project:

1. Create a Vercel project with **Root Directory** `backend` (Python is detected from `backend/requirements.txt`).
2. Set environment variables (Project → Settings → Environment Variables):
   - `DATABASE_URL` — the Neon PostgreSQL connection string (Neon's value includes `sslmode=require`)
   - `TAVILY_API_KEY`, `GROQ_API_KEY`
   - optional overrides: `GROQ_MODEL`, `CORS_ORIGINS` (comma-separated; include the frontend origin)
3. Apply Alembic migrations to the Neon database **once**, from the repository root (migrations intentionally live outside the serverless bundle):

   ```bash
   DATABASE_URL="<neon-connection-string>" alembic upgrade head
   ```

4. Deploy. `backend/api/index.py` exposes the ASGI app and `backend/vercel.json` rewrites all paths to it, so `/health`, `/docs` and `/v1/*` are served at the deployment root.

## Verification

```bash
pytest -q                      # deterministic suite — no network, no API credits
ruff check backend tests migrations
ruff format --check backend tests migrations
cd frontend
npm run typecheck
npm run build
```

CI runs all of the above (backend tests also against a Postgres 16 service container, plus `alembic upgrade head` and a migration drift check) on every push and pull request.

## API surface

- `GET /health`
- `GET /v1/campaigns`
- `POST /v1/campaigns`
- `DELETE /v1/campaigns/{id}` — deletes only campaigns with no prospects; history-bearing campaigns are refused with 409 and counts
- `GET /v1/prospects`
- `POST /v1/prospects/discover`
- `GET /v1/prospects/{id}`
- `GET /v1/workflow-runs`
- `GET /v1/workflow-runs/{id}`
- `POST /v1/workflow-runs/{id}/approval`
- `GET /v1/dashboard/summary`

## Environment variables

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `DATABASE_URL` or `POSTGRES_SERVER/PORT/USER/PASSWORD/DB` | yes | localhost compose values | PostgreSQL connection |
| `TAVILY_API_KEY` | for discovery | — | Web search provider |
| `GROQ_API_KEY` | for discovery | — | LLM provider |
| `GROQ_MODEL` | no | `openai/gpt-oss-120b` | Groq chat model |
| `GROQ_PRICE_PER_M_INPUT_TOKENS` | no | `0.15` | Estimated cost accounting (USD / 1M input tokens) |
| `GROQ_PRICE_PER_M_OUTPUT_TOKENS` | no | `0.66` | Estimated cost accounting (USD / 1M output tokens) |
| `SEARCH_TIMEOUT_SECONDS` | no | `15` | Tavily request timeout |
| `LLM_TIMEOUT_SECONDS` | no | `30` | Groq request timeout |
| `LLM_MAX_TOKENS` | no | `2048` | Completion cap per agent step |
| `LLM_MAX_TOKENS_ESCALATED` | no | `4096` | One-shot escalated budget when a step is cut off mid-JSON by the token cap |
| `MAX_RETRIES` | no | `2` | Provider retries for transient failures |
| `RETRY_BASE_DELAY_SECONDS` | no | `0.5` | Exponential backoff base |
| `RETRY_MAX_DELAY_SECONDS` | no | `8` | Backoff ceiling |
| `OUTREACH_MAX_REVISIONS` | no | `2` | Bound on critic-driven draft revisions |
| `CORS_ORIGINS` | no | `localhost:3000,localhost:8000` | Comma-separated allowed origins |

## Architecture choices

1. **Company and Prospect are separate.** A company is factual identity; a prospect is that company evaluated inside one campaign.
2. **Evidence is first-class.** Agent conclusions can be inspected against persisted sources; web excerpts are framed as untrusted data in every prompt.
3. **Business state is durable.** PostgreSQL owns truth; the LLM context does not.
4. **Agent boundaries are explicit.** Search, research, qualification, outreach and critique are separate steps with observable events — and the critic can drive a *bounded* revision of the outreach draft rather than rubber-stamping it.
5. **Human approval is a workflow state transition.** It is not a decorative UI action, and the gate coerces critic output defensively.
6. **Providers are replaceable and testable.** Production uses real providers; tests use deterministic fakes so CI never spends API credits.

## License

MIT — see [LICENSE](LICENSE).
