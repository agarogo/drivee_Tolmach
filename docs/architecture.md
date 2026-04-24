# Архитектура Толмач by Drivee

## High-Level System Architecture

```mermaid
flowchart LR
    U[Non-tech user] --> FE[React/Vite dark UI]
    FE --> API[FastAPI API]
    API --> AUTH[JWT auth]
    API --> ORCH[AI workflow orchestrator]
    ORCH --> RET[Semantic retrieval]
    ORCH --> CONF[Confidence scoring]
    ORCH --> SQLGEN[SQL planner and generator]
    SQLGEN --> GR[Guardrails validator]
    GR --> EXEC[Safe read-only executor]
    EXEC --> PG[(PostgreSQL)]
    PG --> DATA[Drivee dataset: orders cities drivers clients]
    PG --> TOLMACH[tolmach schema: queries reports schedules traces]
    ORCH --> TRACE[query_events and sql_guardrail_logs]
    FE --> TRACE
    API --> PHX[Phoenix/OpenTelemetry optional]
```

## AI Workflow / Orchestration

```mermaid
flowchart TD
    A[User question] --> B[Query Interpreter]
    B --> C[Semantic Retrieval]
    C --> D[Confidence Scoring]
    D -->|High >= 85| E[SQL Planner]
    D -->|Medium 55-84| CL[Clarification Required]
    D -->|Low invalid| CL
    B -->|Dangerous intent| BL[Blocked]
    E --> F[SQL Generator]
    F --> G[Guardrails Validator]
    G -->|Blocked| BL
    G -->|Validated SELECT| H[Safe SQL Executor]
    H -->|DB error| AF[Auto-Fix Node max 2]
    AF --> G
    H -->|Success| I[Chart Recommendation]
    I --> J[Answer Composer]
    J --> K[Chat Result UI]
```

## Userflow

```mermaid
flowchart TD
    A[Open app] --> B[Login]
    B --> C[Analytics home]
    C --> D[Templates, history, hints]
    D --> E[User enters Russian question]
    E --> F[LLM extracts structured intent]
    F --> G[Server compiler builds semantic SQL plan]
    G --> H{Confidence high?}
    H -->|No| I[Clarification question]
    I --> E
    H -->|Yes| J{Guardrails + EXPLAIN cost safe?}
    J -->|No| K[Blocked request]
    J -->|Yes| L[Read-only SQL execution]
    L --> M{Result received?}
    M -->|No| N[Auto-fix SQL max 2]
    N -->|Fixed| L
    N -->|Failed| O[Error with help]
    M -->|Yes| P[Query result page]
    P --> Q[Explainability, semantic plan, DB explain, SQL, confidence, table, chart, AI answer]
    Q --> R[Save report]
    R --> S[Configure schedule]
    S --> T[Reports and Schedule pages]
```

## Database ER Diagram

```mermaid
erDiagram
    CITIES ||--o{ DRIVERS : has
    CITIES ||--o{ CLIENTS : has
    CITIES ||--o{ ORDERS : contains
    DRIVERS ||--o{ ORDERS : receives_tenders
    CLIENTS ||--o{ ORDERS : creates

    USERS ||--o{ QUERIES : runs
    USERS ||--o{ REPORTS : owns
    USERS ||--o{ TEMPLATES : creates
    QUERIES ||--o{ QUERY_EVENTS : traces
    QUERIES ||--o{ SQL_GUARDRAIL_LOGS : validates
    QUERIES ||--o{ QUERY_CLARIFICATIONS : asks
    QUERIES ||--o{ REPORTS : source
    REPORTS ||--o{ REPORT_VERSIONS : versions
    REPORTS ||--o{ SCHEDULES : runs
    REPORTS ||--o{ REPORT_RECIPIENTS : sends_to
    SCHEDULES ||--o{ SCHEDULE_RUNS : history
```

## Query Lifecycle State Diagram

```mermaid
stateDiagram-v2
    [*] --> idle
    idle --> running: POST /queries/run
    running --> clarification_required: confidence 55-84 or low ambiguity
    clarification_required --> running: POST /queries/{id}/clarify
    running --> blocked: dangerous intent or guardrail failed
    running --> sql_error: DB execution error
    sql_error --> autofix_running: auto-fix attempt
    autofix_running --> running: SQL fixed and revalidated
    autofix_running --> autofix_failed: attempts exhausted
    running --> success: rows returned
    blocked --> [*]
    success --> [*]
    autofix_failed --> [*]
```

## Backend Modules

- `app/ai/interpreter.py` - NL interpretation: intent, metric, dimensions, filters, period, ambiguity flags.
- `app/ai/retrieval.py` - domain retrieval from semantic layer, templates, and few-shot examples.
- `app/ai/confidence.py` - explicit confidence model with high/medium/low bands.
- `app/ai/planner.py` - safe SQL plan from intent and retrieved semantics.
- `app/ai/generator.py` - SELECT-only SQL generation from plan.
- `app/ai/orchestrator.py` - workflow runner, trace events, clarification, auto-fix, answer composition.
- `services/guardrails.py` - parse-tree validation, denylist, table/column whitelist, policies, limit injection.
- `services/query_runner.py` - safe executor that accepts only `ValidatedSQL`.
- `services/bootstrap.py` - demo users, Drivee dataset, semantic terms, templates, policies, report/schedule seed.
- `alembic/` - PostgreSQL migrations, including `tolmach` schema and Drivee marts.

## Database Split

- Public schema: Drivee read-only dataset tables `orders`, `cities`, `drivers`, `clients`.
- Public views: `mart_orders`, `mart_tenders`, `mart_city_daily`, `mart_driver_daily`, `mart_client_daily`.
- `tolmach` schema: platform tables such as `users`, `queries`, `reports`, `schedules`, `templates`, `semantic_layer`, `query_events`, `sql_guardrail_logs`.

## MVP Decisions

- The UI remains on React/Vite to keep delivery focused inside the existing project.
- The AI contour now uses a real LLM as the primary structured-intent node; regex/rule logic remains only as a fallback path.
- LLM output is never executed as SQL directly; the server compiles SQL from semantic-layer keys and then validates it.
- Guardrails include EXPLAIN-based cost gating before execution.
- Auto-fix is intentionally capped at 2 attempts.
- Phoenix/OpenTelemetry runs in Docker Compose; persisted traces stay available for developers without cluttering the main chat UI.
