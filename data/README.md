В этой MVP-версии внешние CSV не нужны.

Alembic создаёт PostgreSQL-схему, а backend при первом старте добавляет demo seed:

- пользователей `tolmach.users`;
- Drivee dataset: `cities`, `drivers`, `clients`, `orders`;
- marts: `mart_orders`, `mart_tenders`, `mart_city_daily`, `mart_driver_daily`, `mart_client_daily`;
- semantic layer terms;
- few-shot semantic examples;
- templates;
- access policies;
- demo report, schedule, recipients, schedule run history.
