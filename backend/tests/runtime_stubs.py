from __future__ import annotations

import os
import sys
import types

from pydantic import BaseModel


def install_runtime_stubs() -> None:
    os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
    os.environ.setdefault("FRONTEND_ORIGIN", "http://localhost:5173")

    if "pydantic_settings" not in sys.modules:
        stub = types.ModuleType("pydantic_settings")

        class StubBaseSettings(BaseModel):
            def __init__(self, **data):
                merged = dict(data)
                for name in self.__class__.model_fields:
                    env_key = name.upper()
                    if name not in merged and env_key in os.environ:
                        merged[name] = os.environ[env_key]
                super().__init__(**merged)

        def settings_config_dict(**kwargs):
            return kwargs

        stub.BaseSettings = StubBaseSettings
        stub.SettingsConfigDict = settings_config_dict
        sys.modules["pydantic_settings"] = stub

    if "sqlglot" not in sys.modules:
        sqlglot = types.ModuleType("sqlglot")
        expressions = types.ModuleType("sqlglot.expressions")

        class Expression:
            def __init__(self, sql_text: str = "") -> None:
                self._sql_text = sql_text

            def sql(self, dialect: str | None = None) -> str:
                return self._sql_text

            def dump(self):
                return {"sql": self._sql_text}

            def find_all(self, _kind):
                return []

        class Table(Expression):
            db = ""
            name = ""

        class Column(Expression):
            table = ""
            name = ""

        class Star(Expression):
            pass

        def parse_one(sql_text: str, read: str | None = None):
            return Expression(sql_text)

        def parse(sql_text: str, read: str | None = None):
            return [Expression(sql_text)]

        expressions.Expression = Expression
        expressions.Table = Table
        expressions.Column = Column
        expressions.Star = Star
        sqlglot.parse_one = parse_one
        sqlglot.parse = parse
        sqlglot.expressions = expressions
        sys.modules["sqlglot"] = sqlglot
        sys.modules["sqlglot.expressions"] = expressions

    import sqlalchemy.ext.asyncio as sqlalchemy_asyncio

    if not getattr(sqlalchemy_asyncio, "_stage2_runtime_stubbed", False):
        def fake_create_async_engine(*args, **kwargs):
            return object()

        class DummySessionMaker:
            def __call__(self, *args, **kwargs):
                raise RuntimeError("AsyncSessionLocal is not available in stubbed tests.")

        sqlalchemy_asyncio.create_async_engine = fake_create_async_engine
        sqlalchemy_asyncio.async_sessionmaker = lambda *args, **kwargs: DummySessionMaker()
        sqlalchemy_asyncio._stage2_runtime_stubbed = True
