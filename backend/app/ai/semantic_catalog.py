from __future__ import annotations

from app.semantic.service import (
    SemanticCatalog,
    SemanticDimensionDefinition as SemanticCatalogDimension,
    SemanticMetricDefinition as SemanticCatalogMetric,
    load_semantic_catalog,
)

SemanticCatalogEntry = SemanticCatalogMetric | SemanticCatalogDimension

__all__ = [
    "SemanticCatalog",
    "SemanticCatalogEntry",
    "SemanticCatalogMetric",
    "SemanticCatalogDimension",
    "load_semantic_catalog",
]
