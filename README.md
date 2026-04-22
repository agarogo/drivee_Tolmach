# Толмач

Self-service AI-аналитика: пользователь задаёт вопрос на русском, система строит безопасный SQL, выполняет его на демо-БД, показывает объяснение, таблицу и график.

## Стек

- FastAPI + SQLAlchemy + PostgreSQL
- JWT-авторизация с ролями `user` и `admin`
- React + TypeScript + React Query + Recharts
- Docker Compose для локального демо
- Text-to-SQL через локальную Ollama: `qwen3:4b`

## Быстрый запуск

```bash
cp .env.example .env
ollama pull qwen3:4b
docker compose up --build
```

Откройте:

- Frontend: `http://localhost:5173`
- Backend docs: `http://localhost:8000/docs`

При первом запуске backend создаёт таблицы и демо-данные: пользователей, города, заказы, отмены, шаблоны.

## Демо-аккаунты

- User: `user@tolmach.local` / `user123`
- Admin: `admin@tolmach.local` / `admin123`

Также можно зарегистрировать нового пользователя через форму. Роль по умолчанию `user`; для проверки админки в форме регистрации доступен выбор `admin`.

## Переменные окружения

См. `.env.example`.

- `DATABASE_URL` - PostgreSQL DSN для backend
- `JWT_SECRET` - секрет подписи JWT
- `FRONTEND_ORIGIN` - origin фронтенда для CORS
- `LLM_PROVIDER` - по умолчанию `ollama`
- `LLM_MODEL` - по умолчанию `qwen3:4b`
- `OLLAMA_BASE_URL` - адрес локальной Ollama. Для Docker Desktop используйте `http://host.docker.internal:11434`, для запуска backend без Docker - `http://localhost:11434`
- `LLM_TEMPERATURE` - температура генерации SQL

Перед запуском убедитесь, что Ollama отвечает:

```bash
ollama serve
ollama pull qwen3:4b
```

## Что работает в демо

1. Регистрация и вход.
2. Кнопка `Новый запрос` создаёт новый чат.
3. Шаблоны заполняют поле ввода:
   - `Еженедельный KPI` -> `Покажи KPI за последнюю неделю по дням`
   - `Отчёт по регионам` -> `Сравни отмены по федеральным округам`
4. Запрос `покажи выручку по топ-10 городам за последние 30 дней` возвращает объяснение, SQL, таблицу и столбчатый график.
5. История чатов сохраняется и загружается после перезагрузки.
6. Сообщения открываются последними 50, при прокрутке вверх догружаются предыдущие.
7. `DROP TABLE users` блокируется guardrails.
8. Администратор видит `/admin/logs`: вопрос, SQL, статус, время, промпт, raw-ответ и ошибки.
9. Ответ можно сохранить как отчёт и настроить демо-рассылку.

## API

- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`
- `GET /api/chats`
- `POST /api/chats`
- `GET /api/chats/{chat_id}/messages?limit=50&offset=0`
- `POST /api/chats/{chat_id}/messages`
- `GET /api/templates`
- `POST /api/templates`
- `GET /api/reports`
- `POST /api/reports`
- `POST /api/reports/{report_id}/schedule`
- `GET /admin/logs`

## Guardrails

Перед выполнением SQL система:

- разрешает только `SELECT` / `WITH`;
- блокирует `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE` и другие опасные операции;
- запрещает таблицы вне аналитического слоя;
- запрещает колонки `password`, `password_hash`, `credit_card`, `ssn`;
- добавляет `LIMIT 1000`, если лимит отсутствует;
- выполняет запрос с `statement_timeout = 5000 ms`.
