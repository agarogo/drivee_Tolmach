# Single database mode

The project now uses one PostgreSQL connection string only:

```env
DATABASE_URL=postgresql://postgres:postgres@db:5432/tolmach
```

All product data and analytics data live in the same database, separated by schemas:

- `app` — users, sessions, chats, semantic catalog, reports, schedules, audit/cache;
- `raw` / `staging` — ingestion and typed normalization;
- `dim` / `fact` / `mart` — governed analytics tables.

`docker-compose.yml` and `.env.example` no longer emit `PLATFORM_DATABASE_URL` or `ANALYTICS_DATABASE_URL`.
The settings module still accepts those old variables only as a legacy fallback, but internally both old names are normalized to `DATABASE_URL` and point to the same engine.
