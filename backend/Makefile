.PHONY: check smoke fmt lint test migrate

check:
	python -m compileall -q app alembic
	python -c "from app.main import app; print('app import ok:', app.title)"

smoke:
	python -m app.wait_for_db
	alembic upgrade head
	python -m app.bootstrap_cli

fmt:
	black app tests

lint:
	ruff check app tests

test:
	pytest

migrate:
	alembic upgrade head
