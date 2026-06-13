"""Guarda de drift — detecta read-models divergindo do schema do master-data."""

from __future__ import annotations

import pytest

from inventia_spoke_sdk.masterdata import (
    ReadBase,
    SchemaDriftError,
    assert_no_drift,
    check_models_against,
)


def _schema_from_models() -> dict[str, set[str]]:
    """Schema 'real' simulado = exatamente o dos read-models (sem drift)."""
    return {name: set(table.columns.keys()) for name, table in ReadBase.metadata.tables.items()}


def test_no_drift_when_schema_matches() -> None:
    assert check_models_against(_schema_from_models()) == []
    assert_no_drift(_schema_from_models())  # não levanta


def test_extra_columns_in_master_data_are_ok() -> None:
    # master-data tem MAIS colunas — read-model mapeia subconjunto: sem drift.
    schema = _schema_from_models()
    schema["companies"].add("coluna_nova_do_master_data")
    assert check_models_against(schema) == []


def test_missing_column_is_drift() -> None:
    schema = _schema_from_models()
    schema["companies"].discard("legal_name")
    problems = check_models_against(schema)
    assert any("companies.legal_name" in p for p in problems)
    with pytest.raises(SchemaDriftError, match="legal_name"):
        assert_no_drift(schema)


def test_missing_table_is_drift() -> None:
    schema = _schema_from_models()
    del schema["units_of_measure"]
    problems = check_models_against(schema)
    assert any("units_of_measure" in p for p in problems)
    with pytest.raises(SchemaDriftError):
        assert_no_drift(schema)
