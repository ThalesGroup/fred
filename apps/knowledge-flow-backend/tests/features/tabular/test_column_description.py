import pytest

from knowledge_flow_backend.features.tabular.structures import TabularColumnDescription, TabularColumnSchema


@pytest.mark.parametrize("dtype", ["string", "datetime", "boolean", "unknown"])
def test_non_numeric_columns_omit_bounds_and_unused_fields(dtype):
    column = TabularColumnDescription(name="value", dtype=dtype)
    assert column.model_dump() == {"name": "value", "dtype": dtype}
    assert column.model_dump(exclude_none=True) == {"name": "value", "dtype": dtype}


@pytest.mark.parametrize("dtype", ["integer", "float"])
def test_numeric_columns_retain_unknown_bounds_even_when_none_is_excluded(dtype):
    column = TabularColumnDescription(name="value", dtype=dtype)
    assert column.model_dump(exclude_none=True) == {"name": "value", "dtype": dtype, "min_value": None, "max_value": None}


def test_legacy_classification_projects_exact_categories_without_legacy_flags():
    stored = TabularColumnSchema.model_validate({"name": "status", "dtype": "string", "is_categorical": True, "has_two_values": True, "sample_values": ["LOW", "High"]})
    assert "has_two_values" not in stored.model_dump()
    assert TabularColumnDescription.from_stored(stored, values_read=True).model_dump() == {"name": "status", "dtype": "string", "categorical_values": ["LOW", "High"]}
    assert TabularColumnDescription.from_stored(stored).model_dump() == {"name": "status", "dtype": "string"}


def test_serialization_keeps_the_declared_openapi_schema():
    schema = TabularColumnDescription.model_json_schema(mode="serialization")
    assert set(schema["properties"]) == {"name", "dtype", "categorical_values", "min_value", "max_value"}
