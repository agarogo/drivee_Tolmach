# Архитектура Толмача

## Поток запроса

```mermaid
flowchart LR
    A[React chat] --> B[FastAPI /api/chats/:id/messages]
    B --> C[Load last 10 messages]
    C --> D[TextToSqlService]
    D --> O[Ollama qwen3:4b]
    O --> E[SQL Guardrails]
    E -->|ok| F[PostgreSQL query]
    E -->|blocked| G[Assistant error]
    F --> H[Chart recommender]
    H --> I[Save assistant message]
    I --> J[Admin query log]
```

## Backend

- `auth.py` - PBKDF2 password hashing and signed JWT.
- `models.py` - users, chats, messages, templates, reports, query logs, demo analytics tables.
- `services/prompts.py` - schema, semantic layer and JSON prompt for the model.
- `services/llm_providers.py` - Ollama provider for `qwen3:4b` plus deterministic fallback.
- `services/nl2sql.py` - thin service for provider selection and 5-minute cache.
- `services/guardrails.py` - SQL safety checks before execution.
- `services/query_runner.py` - PostgreSQL execution with statement timeout.
- `services/bootstrap.py` - demo users, templates, cities, orders, cancellations.

## Данные

```mermaid
erDiagram
    USERS ||--o{ CHATS : owns
    CHATS ||--o{ MESSAGES : stores
    USERS ||--o{ REPORTS : saves
    USERS ||--o{ QUERY_LOGS : creates
    CITIES ||--o{ ORDERS : contains
    CITIES ||--o{ CANCELLATIONS : contains
    ORDERS ||--o{ CANCELLATIONS : may_have

    USERS {
      int id
      string email
      string password_hash
      string role
    }

    CHATS {
      int id
      int user_id
      string title
    }

    MESSAGES {
      int id
      int chat_id
      string role
      text content
      json payload
    }

    QUERY_LOGS {
      int id
      int user_id
      text question
      text generated_sql
      string status
      int duration_ms
      text prompt
      text raw_response
    }
```
