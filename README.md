# Толмач by Drivee

Production-like MVP self-service аналитики: пользователь задаёт вопрос на русском языке, система интерпретирует запрос, ищет бизнес-термины в semantic layer, считает confidence, генерирует безопасный read-only SQL, выполняет его в PostgreSQL, показывает explainability, таблицу, график, AI summary, отчёты и расписание.

## Стек

- Backend: FastAPI, SQLAlchemy 2.0 async, asyncpg, Alembic, PostgreSQL.
- Frontend: React/Vite, TypeScript, TanStack Query, Recharts.
- AI workflow: interpreter, semantic retrieval, confidence scoring, SQL planner/generator, guardrails, safe executor, auto-fix, answer composer.
- Observability: persisted `query_events` and `sql_guardrail_logs`, Phoenix/OpenTelemetry container in Docker Compose.

## Быстрый запуск

```bash
cp .env.example .env
docker compose up --build
```

Открыть:

- Frontend: `http://localhost:5173`
- Backend docs: `http://localhost:8000/docs`
- Phoenix traces: `http://localhost:6006`

При старте backend выполняет только `alembic upgrade head`.
Demo data больше не seed-ится автоматически и запускается только явно через `python -m app.bootstrap_cli`.

### Подключение к PostgreSQL

Backend всегда использует `DATABASE_URL` из `.env`, если переменная задана. Это нужно для production/external PostgreSQL: миграции Alembic выполняются именно в этой БД.
Demo bootstrap по умолчанию блокируется для non-local DSN.

Для локального compose можно оставить значение из `.env.example`:

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/tolmach
```

Для внешней БД укажите DSN провайдера:

```bash
DATABASE_URL=postgresql://user:password@host:5432/database
```

Система нормализует `postgresql://` в async SQLAlchemy URL автоматически.

### Если backend падает на миграции

Если в логах есть `relation "cities" already exists`, значит Docker использует старый PostgreSQL volume с прежней demo-схемой. В `docker-compose.yml` задан отдельный named volume `drivee-tolmach-postgres-data`, чтобы новый MVP стартовал на чистой локальной БД без удаления старых данных.

Если нужен полный сброс локальной БД с потерей данных, остановите compose и удалите volume:

```bash
docker compose down -v
docker compose up --build
```

## Демо-аккаунты

- User: `user@tolmach.local` / `user123`
- Admin: `admin@tolmach.local` / `admin123`

## Структура

```text
backend/
  alembic/
  app/
    ai/                  # interpreter, retrieval, confidence, planner, generator, orchestrator
    services/            # guardrails, safe executor, bootstrap
    api.py
    auth.py
    config.py
    db.py
    models.py
    schemas.py
  tests/
frontend/
  src/
    api.ts
    types.ts
    components.tsx
    App.tsx
docs/
  architecture.md
  demo_script.md
```

## База данных

- Public schema: Drivee dataset `orders`, `cities`, `drivers`, `clients`.
- Если в production БД есть raw-таблица `train`, миграция `20260423_0002` использует её как источник фактов для `mart_orders` и `mart_tenders`; `orders` остаётся совместимой demo-таблицей.
- Public read-only marts: `mart_orders`, `mart_tenders`, `mart_city_daily`, `mart_driver_daily`, `mart_client_daily`.
- `tolmach` schema: `users`, `invites`, `refresh_tokens`, `queries`, `query_clarifications`, `query_events`, `sql_guardrail_logs`, `reports`, `report_versions`, `schedules`, `schedule_runs`, `report_recipients`, `templates`, `semantic_layer`, `semantic_examples`, `access_policies`, `chart_preferences`.

Важно: одна строка dataset соответствует комбинации `order_id + tender_id`. Метрики уровня заказа считаются через `mart_orders` и `COUNT(DISTINCT order_id)`.

## API

- `POST /auth/login`
- `GET /auth/me`
- `POST /queries/run`
- `POST /queries/{id}/clarify`
- `GET /queries/history`
- `GET /queries/{id}`
- `POST /reports`
- `GET /reports`
- `GET /reports/{id}`
- `PATCH /reports/{id}`
- `POST /reports/{id}/run`
- `POST /reports/{id}/share`
- `GET /templates`
- `POST /templates`
- `GET /schedules`
- `POST /schedules`
- `PATCH /schedules/{id}`
- `POST /schedules/{id}/toggle`
- `GET /semantic-layer`
- `POST /semantic-layer`
- `GET /health`
- `GET /metrics`
- `GET /traces-link`

Compatibility routes `/api/chats`, `/api/reports`, `/api/templates` оставлены для прежнего shell.

## Guardrails

Перед выполнением SQL система проверяет:

- только `SELECT` / `WITH`;
- denylist write/DDL keywords;
- single statement;
- parse tree через `sqlglot`;
- table whitelist;
- role-based `access_policies`;
- forbidden columns;
- запрет `SELECT *`;
- limit injection/cap;
- cost heuristics;
- timeout через `statement_timeout`.

Safe executor принимает только объект `ValidatedSQL`, который возвращает validator.

## Confidence

- High `>= 85`: SQL выполняется сразу.
- Medium `55-84`: выполнение останавливается, UI показывает уточняющий вопрос.
- Low/dangerous: clarify или blocked в зависимости от причины.

## Проверки

```bash
python -m compileall backend/app backend/alembic
$env:PYTHONPATH="backend"; python -m unittest discover backend/tests
cd frontend
npm run build
```

## Документация

- Архитектура и Mermaid diagrams: `docs/architecture.md`
- Демо-сценарий: `docs/demo_script.md`

## Дальнейшие улучшения

- Подключить реальный LLM provider к planner/generator как controlled node.
- Добавить embeddings для semantic retrieval вместо MVP lexical scoring.
- Подключить APScheduler/Celery для реального фонового запуска schedules.
- Подключить Phoenix/OpenTelemetry exporter для внешних distributed traces.
- Добавить RBAC UI для `access_policies` и semantic layer governance.
- Добавить реальные CSV/PNG export jobs и email delivery.
