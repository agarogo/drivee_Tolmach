# Tolmach by Drivee

Production-ready MVP for governed self-service analytics with FastAPI, React, PostgreSQL, scheduler workers, and live LLM orchestration.

## Architecture

```text
frontend (React + Vite)
  -> backend API (FastAPI)
    -> platform DB (app schema: users, chats, sessions, semantic layer, reports)
    -> analytics DB (fact/dim/mart tables, read-only SQL execution)
    -> scheduler worker (scheduled reports, deliveries, artifacts)
    -> Ollama or production LLM gateway
    -> Phoenix / OpenTelemetry
```

### Runtime components

- `frontend`: React + TypeScript UI with cookie-based auth and CSRF headers.
- `backend`: FastAPI API, session auth, semantic retrieval, LLM orchestration, SQL guardrails, report APIs.
- `db`: PostgreSQL for local end-to-end startup.
- `scheduler`: background worker that executes schedules and deliveries.
- `ollama`: local LLM runtime used by default in Docker Compose.
- `phoenix`: trace and prompt observability endpoint.

### Database split

- `DATABASE_URL`: the single PostgreSQL database used by the whole product. Application metadata, sessions, chats, semantic catalog, reports, audit tables and governed analytics schemas all live in this database under separate schemas.
- Local `docker-compose` points both URLs to the same PostgreSQL instance so the stack is runnable out of the box.
- In production you can split them, but the analytics database must already contain the governed `fact.*`, `dim.*`, and `mart.*` tables used by the executor.

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Frontend: `http://localhost:5173`
- Backend docs: `http://localhost:8000/docs`
- Phoenix: `http://localhost:6006`

First startup may take several minutes because `ollama-init` pulls `${LLM_MODEL}` before the backend becomes healthy.

### Demo accounts

- `user@tolmach.local` / `user123`
- `admin@tolmach.local` / `admin123`

## Security Model

- CORS is restricted to `FRONTEND_ORIGINS`; wildcard origins are rejected.
- Auth is cookie-only. No bearer tokens and no auth data in `localStorage`.
- Session cookie is `HttpOnly`.
- CSRF protection requires cookie + header match on every non-safe request.
- SQL execution is read-only and passes semantic compilation plus guardrails before reaching PostgreSQL.

## AI Pipeline

1. Frontend sends the question with browser cookies and the CSRF header.
2. Backend restores chat context and semantic retrieval candidates.
3. LLM classifies `answer_type_key` (`chat_help`, `single_value`, `comparison_top`, `trend`, `distribution`, `table`, `full_report`).
4. LLM extracts structured intent.
5. If ambiguity remains, LLM produces clarification options.
6. LLM drafts an intermediate SQL plan.
7. Semantic compiler turns the draft into governed SQL only from approved metrics, dimensions, and filters.
8. Guardrails validate read-only SQL, inject limits, run `EXPLAIN`, and reject unsafe queries.
9. Executor runs the validated SQL against `DATABASE_URL`.
10. LLM optionally writes the factual answer summary from returned rows.
11. API returns the answer envelope plus telemetry:

```json
{
  "provider": "ollama",
  "llm_provider": "ollama",
  "llm_model": "qwen3:4b",
  "llm_used": true,
  "fallback_used": false,
  "retrieval_used": true
}
```

## Models and Providers

- Default local provider: `LLM_PROVIDER=ollama`
- Default local model: `LLM_MODEL=qwen3:4b`
- Production provider: `LLM_PROVIDER=production` with an OpenAI-compatible `/chat/completions` endpoint
- Rule fallback is allowed only outside `APP_ENV=demo|production` and only when `LLM_STRICT_MODE=false` and `LLM_RULE_FALLBACK_ENABLED=true`

### Fail-fast behavior

- If strict mode is enabled and the LLM is unavailable, the request returns `503` instead of silently switching to fake AI.
- If fallback is used outside strict mode, the backend logs a warning and the API response exposes `fallback_used=true`.

## How To Verify The LLM Is Real

1. Start the stack with `docker compose up --build`.
2. Confirm model pull and API startup:

```bash
docker compose logs -f ollama ollama-init backend
```

Manual model check:

```bash
docker exec <ollama_container> ollama list
```

The list must contain `qwen3:4b` (or your configured `LLM_MODEL`). If the model is missing, `ollama-init` now exits with an error and the backend will not start.

3. Sign in through the UI.
4. Run a question such as `show revenue by top 10 cities for the last 30 days`.
5. Check the response in browser devtools or `GET /queries/history` and confirm:

- `llm_used` is `true`
- `fallback_used` is `false`
- `llm_provider` is `ollama` or `production`
- `llm_model` is populated

If you see `provider=fallback` or `llm_used=false`, the request was degraded and the logs should show why.

## Example: Request -> SQL -> Answer

Request:

```text
show revenue by top 10 cities for the last 30 days
```

Representative SQL shape:

```sql
SELECT
  dim_city.city_name AS city,
  SUM(fo.price_order_local) FILTER (WHERE fo.status_order = 'done') AS revenue
FROM fact.orders AS fo
JOIN dim.cities AS dim_city ON dim_city.city_id = fo.city_id
WHERE fo.order_day >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY dim_city.city_name
ORDER BY revenue DESC
LIMIT 10;
```

Representative answer:

```text
Revenue: Tokyo leads with 1,240,000. Osaka and Almaty follow.
```

The exact SQL can differ by semantic compilation strategy, but it must stay inside approved tables, columns, filters, and read-only guardrails.

## Docker Compose Services

- `db`: local PostgreSQL with healthcheck.
- `ollama`: local LLM runtime.
- `ollama-init`: one-shot model pull so `/queries/run` is usable after startup.
- `backend`: runs migrations, seeds demo data, then starts FastAPI.
- `scheduler`: background report worker with heartbeat healthcheck.
- `frontend`: Vite dev server.
- `phoenix`: prompt/tracing observability.

## Developer Verification

```bash
python -m compileall backend/app backend/alembic
python -m pip install -r backend/requirements.txt
python -m unittest discover backend/tests
./scripts/test_backend.ps1
cd backend
python -m unittest discover tests
cd ../frontend
npm install
npm run build
cd ..
docker compose config
```

## Key API Paths

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`
- `POST /queries/run`
- `POST /queries/{query_id}/clarify`
- `GET /queries/history`
- `GET /queries/{query_id}`
- `POST /reports`
- `GET /reports`
- `GET /schedules`
- `GET /health`

## Notes

- `docker-compose` seeds demo data automatically on backend startup.
- The frontend uses cookies only; opening old tabs from a bearer-token build is not supported.
- The scheduler is part of the default stack and is expected to stay healthy in `docker compose ps`.
- Host-side unittest discovery from the repo root is supported via `sitecustomize.py`, which adds `backend/` to `PYTHONPATH` automatically.
- `scripts/test_backend.ps1` runs the host suite when local Python deps are installed and falls back to the Dockerized backend suite when they are not.
