# Краткая заметка по реализации

Проект доведён до production-like MVP `Толмач by Drivee`.

Ключевые изменения:

- PostgreSQL-only persistence через SQLAlchemy async и Alembic.
- Platform tables вынесены в схему `tolmach`.
- Drivee dataset представлен таблицами `orders`, `cities`, `drivers`, `clients` и read-only mart views.
- AI-контур разделён на interpreter, retrieval, confidence scoring, planner, generator, guardrails, safe executor, auto-fix, answer composer.
- Добавлены trace tables: `query_events`, `sql_guardrail_logs`, `query_clarifications`.
- Добавлены версии отчётов, расписания, получатели, run history.
- UI перестроен в тёмный Drivee/ChatGPT-like интерфейс с отдельными экранами «Аналитика», «Отчёты», «Шаблоны», «Расписание».
