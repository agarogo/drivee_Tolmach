# Демо-сценарий для жюри

## Подготовка

```bash
cp .env.example .env
docker compose up --build
```

Открыть:

- Frontend: `http://localhost:5173`
- Backend docs: `http://localhost:8000/docs`
- Phoenix, если подключён отдельно: `http://localhost:6006`

## Основной happy path

1. Войти как `user@tolmach.local` / `user123`.
2. На экране «Аналитика» выполнить: `покажи выручку по топ-10 городам за последние 30 дней`.
3. Показать ChatGPT-like flow: во время отправки виден только `loading_confidence`, без технических pipeline steps.
4. После ответа показать KPI cards, график, таблицу, explainability, SQL внутри раскрываемого блока и AI summary.
5. Отметить, что технический trace хранится в БД и Phoenix, но не перегружает основной чат.
6. Сохранить результат как отчёт, включить weekly schedule, добавить получателя.
7. Перейти в «Отчёты»: открыть отчёт, показать версии, recipients, run now.
8. Перейти в «Расписание»: показать next run, last run, status, recipients, run history.

## Clarification path

1. Выполнить: `покажи статистику по городам`.
2. Показать warning-state: confidence medium/low, причины неоднозначности, быстрые варианты выбора.
3. Выбрать вариант уточнения.
4. Показать новый безопасный запуск после уточнения.

## Blocked path

1. Выполнить: `удали всех водителей у которых рейтинг ниже 3.5`.
2. Показать danger-state: запрос остановлен до SQL execution.
3. Показать rule violation и безопасные альтернативы.
4. Пояснить, что guardrail log сохранён в `tolmach.sql_guardrail_logs`.

## Auto-fix path

1. В dev/demo можно временно сломать SQL в сохранённом отчёте, например заменить `price_order_local` на `amount`.
2. Нажать «Запустить сейчас».
3. Backend валидирует SQL и не выполняет unsafe запросы; workflow auto-fix в `/queries/run` ограничен двумя попытками.

## Что подчеркнуть

- Слой данных Drivee отделён от платформенных таблиц `tolmach`.
- Одна строка dataset является уровнем `order_id + tender_id`; метрики заказов считаются через `mart_orders` с `COUNT(DISTINCT order_id)`.
- Guardrails работают до выполнения SQL.
- Confidence не является просто числом LLM: он считается отдельным модулем.
- Explainability показывает semantic terms и выбранный SQL plan.
