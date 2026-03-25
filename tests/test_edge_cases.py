"""Tests for edge cases in data generation — boundary values, empty schemas, large batches."""

import json
import uuid

import pytest

from datagen.engine.generators import (
    gen_boolean, gen_integer, gen_number, gen_string,
    gen_array, gen_datetime, sample_distribution, weighted_choice,
)
from datagen.engine.schema_parser import SchemaParser, generate_value, generate_record


# ---------------------------------------------------------------------------
# Edge cases in generators
# ---------------------------------------------------------------------------

class TestStringEdgeCases:
    def test_empty_enum(self):
        """Schema with empty enum list raises IndexError."""
        schema = {"type": "string", "enum": []}
        with pytest.raises(IndexError):
            gen_string(schema)

    def test_single_enum_value(self):
        schema = {"type": "string", "enum": ["only"]}
        for _ in range(10):
            assert gen_string(schema) == "only"

    def test_pattern_digits_only(self):
        schema = {"type": "string", "pattern": "[0-9]{5}"}
        result = gen_string(schema)
        assert len(result) == 5
        assert result.isdigit()

    def test_format_date(self):
        result = gen_string({"type": "string", "format": "date"})
        assert isinstance(result, str)
        assert len(result) == 10  # YYYY-MM-DD

    def test_format_datetime(self):
        result = gen_string({"type": "string", "format": "date-time"})
        assert isinstance(result, str)
        assert "T" in result

    def test_no_constraints(self):
        result = gen_string({"type": "string"})
        assert isinstance(result, str)


class TestIntegerEdgeCases:
    def test_same_min_max(self):
        schema = {"type": "integer", "minimum": 42, "maximum": 42}
        for _ in range(10):
            assert gen_integer(schema) == 42

    def test_large_range(self):
        schema = {"type": "integer", "minimum": -1000000, "maximum": 1000000}
        result = gen_integer(schema)
        assert -1000000 <= result <= 1000000

    def test_negative_range(self):
        schema = {"type": "integer", "minimum": -100, "maximum": -1}
        for _ in range(20):
            result = gen_integer(schema)
            assert -100 <= result <= -1

    def test_no_constraints(self):
        result = gen_integer({"type": "integer"})
        assert isinstance(result, int)

    def test_single_enum(self):
        schema = {"type": "integer", "enum": [7]}
        assert gen_integer(schema) == 7


class TestNumberEdgeCases:
    def test_zero_range(self):
        schema = {"type": "number", "minimum": 0, "maximum": 0}
        result = gen_number(schema)
        assert result == 0.0

    def test_very_small_range(self):
        schema = {"type": "number", "minimum": 1.0, "maximum": 1.001}
        result = gen_number(schema)
        assert 1.0 <= result <= 1.001

    def test_precision_zero(self):
        schema = {"type": "number", "x-datagen-precision": 0, "minimum": 0, "maximum": 100}
        result = gen_number(schema)
        assert result == int(result)  # Should be a whole number


class TestBooleanEdgeCases:
    def test_always_true(self):
        schema = {"type": "boolean", "x-datagen-weight": 1.0}
        results = [gen_boolean(schema) for _ in range(50)]
        assert all(results)

    def test_always_false(self):
        schema = {"type": "boolean", "x-datagen-weight": 0.0}
        results = [gen_boolean(schema) for _ in range(50)]
        assert not any(results)


class TestDistributionEdgeCases:
    def test_unknown_distribution_type(self):
        """Unknown distribution should fall back gracefully."""
        try:
            val = sample_distribution({"type": "unknown", "min": 0, "max": 10})
            assert isinstance(val, (int, float))
        except (ValueError, KeyError):
            pass  # Acceptable to raise

    def test_poisson_zero_lambda(self):
        val = sample_distribution({"type": "poisson", "lambda": 0})
        assert isinstance(val, (int, float))


class TestWeightedChoice:
    def test_single_item(self):
        result = weighted_choice(["only"], [1.0])
        assert result == "only"

    def test_all_zero_weights(self):
        """All-zero weights should still return something."""
        try:
            result = weighted_choice(["a", "b"], [0, 0])
            assert result in ["a", "b"]
        except (ValueError, ZeroDivisionError):
            pass  # Acceptable to raise


# ---------------------------------------------------------------------------
# Schema parser edge cases
# ---------------------------------------------------------------------------

class TestSchemaParserEdgeCases:
    def test_empty_properties(self):
        schema = {"type": "object", "properties": {}}
        parser = SchemaParser(schema)
        records = parser.generate(count=3)
        assert len(records) == 3
        for r in records:
            assert isinstance(r, dict)

    def test_single_field(self):
        schema = {"type": "object", "properties": {"id": {"type": "string", "format": "uuid"}}}
        parser = SchemaParser(schema)
        records = parser.generate(count=5)
        assert len(records) == 5
        for r in records:
            uuid.UUID(r["id"])  # Should not raise

    def test_count_zero(self):
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        parser = SchemaParser(schema)
        records = parser.generate(count=0)
        assert records == []

    def test_count_one(self):
        schema = {"type": "object", "properties": {"x": {"type": "integer", "minimum": 1, "maximum": 1}}}
        parser = SchemaParser(schema)
        records = parser.generate(count=1)
        assert len(records) == 1
        assert records[0]["x"] == 1

    def test_large_batch(self):
        schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string", "format": "uuid", "x-datagen-unique": True},
                "value": {"type": "integer", "minimum": 0, "maximum": 999999},
            }
        }
        parser = SchemaParser(schema)
        records = parser.generate(count=1000)
        assert len(records) == 1000
        ids = [r["id"] for r in records]
        assert len(set(ids)) == 1000  # All unique

    def test_deeply_nested(self):
        schema = {
            "type": "object",
            "properties": {
                "level1": {
                    "type": "object",
                    "properties": {
                        "level2": {
                            "type": "object",
                            "properties": {
                                "value": {"type": "integer", "minimum": 1, "maximum": 10}
                            }
                        }
                    }
                }
            }
        }
        parser = SchemaParser(schema)
        records = parser.generate(count=3)
        for r in records:
            assert 1 <= r["level1"]["level2"]["value"] <= 10

    def test_mixed_types(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "x-datagen-faker": "person.name"},
                "age": {"type": "integer", "minimum": 0, "maximum": 120},
                "score": {"type": "number", "minimum": 0.0, "maximum": 100.0},
                "active": {"type": "boolean"},
                "tags": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
                "ts": {"type": "string", "format": "date-time"},
            }
        }
        parser = SchemaParser(schema)
        records = parser.generate(count=10)
        for r in records:
            assert isinstance(r["name"], str)
            assert isinstance(r["age"], int)
            assert isinstance(r["score"], (int, float))
            assert isinstance(r["active"], bool)
            assert isinstance(r["tags"], list)
            assert isinstance(r["ts"], str)

    def test_weighted_enum_distribution(self):
        """Heavily weighted enum should skew results."""
        schema = {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["active", "inactive"],
                    "x-datagen-weight": [99, 1],
                }
            }
        }
        parser = SchemaParser(schema)
        records = parser.generate(count=500)
        active_count = sum(1 for r in records if r["status"] == "active")
        assert active_count > 400  # Should be heavily weighted

    def test_null_rate_full(self):
        """100% null rate should produce all nulls."""
        schema = {
            "type": "object",
            "properties": {
                "val": {"type": "string", "x-datagen-null-rate": 1.0}
            }
        }
        parser = SchemaParser(schema)
        records = parser.generate(count=50)
        for r in records:
            assert r["val"] is None

    def test_null_rate_zero(self):
        """0% null rate should produce no nulls."""
        schema = {
            "type": "object",
            "properties": {
                "val": {"type": "string", "x-datagen-faker": "person.name", "x-datagen-null-rate": 0.0}
            }
        }
        parser = SchemaParser(schema)
        records = parser.generate(count=50)
        for r in records:
            assert r["val"] is not None

    def test_allof_merge(self):
        """allOf should merge schemas."""
        schema = {
            "type": "object",
            "allOf": [
                {"properties": {"a": {"type": "integer", "minimum": 1, "maximum": 1}}},
                {"properties": {"b": {"type": "string", "enum": ["x"]}}},
            ]
        }
        parser = SchemaParser(schema)
        records = parser.generate(count=3)
        for r in records:
            assert r["a"] == 1
            assert r["b"] == "x"


# ---------------------------------------------------------------------------
# generate_value and generate_record direct calls
# ---------------------------------------------------------------------------

class TestGenerateValue:
    def test_string_type(self):
        val = generate_value({"type": "string"})
        assert isinstance(val, str)

    def test_integer_type(self):
        val = generate_value({"type": "integer"})
        assert isinstance(val, int)

    def test_number_type(self):
        val = generate_value({"type": "number"})
        assert isinstance(val, (int, float))

    def test_boolean_type(self):
        val = generate_value({"type": "boolean"})
        assert isinstance(val, bool)


class TestGenerateRecord:
    def test_simple_record(self):
        schema = {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "minimum": 5, "maximum": 5}
            }
        }
        record = generate_record(schema)
        assert record["x"] == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
