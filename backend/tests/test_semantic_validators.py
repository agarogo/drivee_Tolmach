import unittest

from app.semantic.validators import (
    validate_dimension_definition,
    validate_metric_definition,
    validate_term_definition,
)


class SemanticValidatorTests(unittest.TestCase):
    def test_metric_validator_rejects_unknown_dimension_reference(self) -> None:
        report = validate_metric_definition(
            {
                "metric_key": "revenue",
                "business_name": "Выручка",
                "description": "Revenue metric.",
                "sql_expression_template": "SUM({base_alias}.price_order_local)",
                "grain": "order",
                "allowed_dimensions": ["city", "unknown_dimension"],
                "allowed_filters": ["city"],
                "default_chart": "bar",
                "safety_tags": ["finance"],
            },
            dimension_keys={"city", "day"},
            supported_grains={"order", "tender"},
        )
        self.assertFalse(report.ok)
        self.assertTrue(any(issue.code == "unknown_allowed_dimension" for issue in report.issues))

    def test_dimension_validator_rejects_invalid_join_path(self) -> None:
        report = validate_dimension_definition(
            {
                "dimension_key": "city",
                "business_name": "Город",
                "table_name": "dim.cities",
                "column_name": "city_name",
                "join_path": "SELECT * FROM dim.cities",
                "data_type": "string",
            },
            allowed_tables={"dim.cities", "fact.orders"},
        )
        self.assertFalse(report.ok)
        self.assertTrue(any(issue.code == "join_prefix" for issue in report.issues))

    def test_term_validator_rejects_missing_mapped_metric(self) -> None:
        report = validate_term_definition(
            {
                "term": "выручка",
                "aliases": ["доход"],
                "mapped_entity_type": "metric",
                "mapped_entity_key": "revenue",
            },
            metric_keys={"orders_count"},
            dimension_keys={"city"},
        )
        self.assertFalse(report.ok)
        self.assertTrue(any(issue.code == "unknown_mapped_entity" for issue in report.issues))


if __name__ == "__main__":
    unittest.main()
