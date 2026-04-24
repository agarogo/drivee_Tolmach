#!/usr/bin/env sh
set -eu
python -m compileall -q app alembic
python -c "from app.main import app; print('app import ok:', app.title)"
alembic upgrade head
pytest -q
