# Stage 1: AI + Safety Foundation

## Что изменилось

- Основной NL -> SQL pipeline переведён с fake AI на real AI path:
  - `semantic layer retrieval`
  - `LLM structured intent extraction`
  - `server-side semantic SQL compiler`
  - `guardrails validation`
  - `EXPLAIN cost gate`
  - `read-only execution`
- Regex/rule-based интерпретация сохранена только как fallback, если LLM provider недоступен.
- Demo bootstrap больше не запускается при старте приложения.
- Demo seed теперь выполняется только явно через CLI.
- Query response хранит:
  - resolved request
  - semantic SQL plan
  - DB explain plan
  - explain cost

## Safety Guarantees

- LLM не пишет итоговый SQL напрямую.
- Итоговый SQL компилируется сервером только из semantic keys.
- `SELECT *` запрещён.
- Выполнение идёт только в `READ ONLY` transaction.
- Перед выполнением делается `EXPLAIN (FORMAT JSON)`.
- Если `Total Cost` выше `SQL_EXPLAIN_MAX_COST`, запрос блокируется.
- На сессию применяются:
  - `statement_timeout`
  - `lock_timeout`
  - `idle_in_transaction_session_timeout`
- Row limit ограничивается policy и global config.

## Локальный запуск

```bash
cp .env.example .env
docker compose up --build
docker compose exec backend python -m app.bootstrap_cli
```

## Явственный bootstrap demo data

Локальный seed:

```bash
docker compose exec backend python -m app.bootstrap_cli
```

Нелокальная БД допускается только явно:

```bash
docker compose exec backend python -m app.bootstrap_cli --allow-nonlocal
```

## Проверки

Backend compile:

```bash
python -m compileall backend/app backend/alembic
```

Backend tests через Docker:

```bash
docker build -t drivee-tolmach-backend-test ./backend
docker run --rm -v "${PWD}/backend:/app" -w /app -e PYTHONPATH=/app -e PLATFORM_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/tolmach -e ANALYTICS_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/tolmach drivee-tolmach-backend-test python -m unittest discover tests
```

Frontend build:

```bash
cd frontend
npm install
npm run build
```
