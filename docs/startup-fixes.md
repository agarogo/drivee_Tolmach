# Startup fixes for single-database Docker mode

This build fixes the runtime blockers found during Docker startup:

1. **Demo bootstrap blocked in Docker**
   - `docker-compose.yml` now runs `python -m app.bootstrap_cli --allow-nonlocal` by default through `BOOTSTRAP_CLI_ARGS`.
   - This is safe for the bundled local Docker database. For a real external database, remove demo bootstrap from the command or set your own bootstrap policy.

2. **Missing `tolmach` database in reused Postgres volumes**
   - `app.wait_for_db` now first connects to the maintenance `postgres` database and creates the target database from `DATABASE_URL` when it is missing.
   - This avoids repeated `FATAL: database "tolmach" does not exist` loops.

3. **Fragile Compose DATABASE_URL default**
   - The Compose default was simplified to one explicit local DSN: `postgresql+asyncpg://postgres:postgres@db:5432/tolmach`.
   - `.env.example` still supports one URL only: `DATABASE_URL`.

## Recommended clean run

```powershell
docker compose down -v
docker compose up --build
```

## Checks

```powershell
docker compose ps
curl http://localhost:8000/health
docker compose exec ollama ollama list
```

If you point `DATABASE_URL` at a real remote database, do **not** run demo bootstrap unless you intentionally want seed data there.
