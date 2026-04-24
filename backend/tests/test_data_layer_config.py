import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlglot import expressions as exp
from app.services.bootstrap import bootstrap_demo_data
from app.services.guardrails import _table_identifier
from sqlglot import parse_one


class DataLayerConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_demo_bootstrap_is_blocked_in_production(self) -> None:
        fake_settings = SimpleNamespace(
            is_production=True,
            demo_bootstrap_allow_nonlocal=False,
            platform_database_url="postgresql://analytics.example.local:5432/drivee",
        )
        with patch("app.services.bootstrap.settings", fake_settings):
            with self.assertRaises(RuntimeError):
                await bootstrap_demo_data(AsyncMock(), allow_nonlocal=False)

    def test_guardrails_keep_schema_qualified_table_names(self) -> None:
        parsed = parse_one("SELECT fo.order_id FROM fact.orders fo")
        table = next(parsed.find_all(exp.Table))
        self.assertEqual(_table_identifier(table), "fact.orders")


if __name__ == "__main__":
    unittest.main()
