# Final runtime hardening notes

This package includes the final emergency fixes applied after live verification exposed backend responsiveness issues.

## Fixed

1. **Ultra-light health route**
   - `/health` and `/api/health` are registered directly in `backend/app/main.py` before the heavy API router.
   - The health route performs no DB, LLM, scheduler, Phoenix, or network calls.
   - It is safe to use for Docker healthchecks and should respond even when Ollama or the scheduler is degraded.

2. **Global query workflow timeout**
   - `QUERY_WORKFLOW_TIMEOUT_SECONDS` was added to settings, `.env.example`, and `docker-compose.yml`.
   - `/queries/run` now wraps the whole NL→SQL workflow in `asyncio.wait_for(...)`.
   - Long LLM/model stalls now return HTTP `504` instead of hanging indefinitely.

3. **Production-style backend command**
   - Docker Compose now starts uvicorn without `--reload`.
   - The backend command uses `exec uvicorn ... --timeout-keep-alive 5` so the container lifecycle and healthchecks are deterministic.

4. **Scheduler heartbeat migration/runtime safety**
   - The package contains the `20260424_0010_worker_heartbeats.py` Alembic migration.
   - Worker heartbeat freshness normalizes naive/aware UTC datetimes.
   - `/admin/scheduler/summary` should not crash merely because the worker is missing or stale.

5. **Typed render-payload guard**
   - Successful typed answers must produce `render_payload`.
   - If a typed successful answer cannot be materialized, the query is blocked with an answer-contract error rather than returning `success` with `render_payload=null`.

6. **Distribution answer correctness**
   - Removed duplicated row accumulation in distribution payload building.

## Verification commands to run locally

```powershell
docker compose down -v
docker compose up --build -d
docker compose ps
curl.exe -sS --max-time 3 http://localhost:8000/health
docker compose exec -T ollama ollama list
docker compose exec -T scheduler python -m app.worker_health_cli
```

Then log in through the UI or API and verify:

```powershell
# After cookie login:
curl.exe -sS --max-time 120 http://localhost:8000/queries/run
```

Expected successful analytics response properties:

```json
{
  "llm_used": true,
  "fallback_used": false,
  "retrieval_used": true,
  "answer_type_key": "...",
  "answer": {
    "render_payload": { "kind": "..." }
  }
}
```

If the configured model is unavailable or too slow in strict/demo mode, `/queries/run` should return a controlled `503` or `504`, not hang.

## Notes

- Docker was not available in the packaging environment used for this handoff, so the final Docker live-run must be executed locally.
- `qwen3:4b` can be slow on CPU-only systems. For faster local verification you may temporarily set `LLM_MODEL` to a smaller Ollama model that supports JSON/tool-like responses, but for final judging keep the model choice documented in `.env.example` and README.


## Single database mode

The project now uses a single `DATABASE_URL`. All application and analytics schemas live in the same PostgreSQL database. The old `PLATFORM_DATABASE_URL` / `ANALYTICS_DATABASE_URL` variables are treated only as legacy fallbacks by settings and are no longer emitted by `.env.example` or `docker-compose.yml`.
