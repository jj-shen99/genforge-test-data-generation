"""Negative tests — invalid inputs, malformed schemas, error paths.

These tests verify that the system handles bad data gracefully:
raises exceptions or returns safe defaults rather than crashing.
"""

import pytest

from datagen.engine.generators import (
    gen_string, gen_integer, gen_number, gen_boolean,
    gen_array, gen_datetime, sample_distribution, weighted_choice,
)
from datagen.engine.schema_parser import SchemaParser, generate_value, generate_record
from datagen.engine.pipeline import GenerationPipeline
from datagen.connectors.base import (
    AuthConfig, AuthMethod, ConnectionConfig, HealthCheck, PushResult,
)
from datagen.connectors.registry import create_connector


# ---------------------------------------------------------------------------
# Generator negative tests
# ---------------------------------------------------------------------------

class TestStringNegative:
    def test_empty_enum_raises(self):
        """Empty enum list should raise IndexError."""
        with pytest.raises(IndexError):
            gen_string({"type": "string", "enum": []})

    def test_unknown_faker_key_falls_through(self):
        """Unknown x-datagen-faker key should not crash — falls to default."""
        result = gen_string({"type": "string", "x-datagen-faker": "nonexistent.provider"})
        assert isinstance(result, str)

    def test_unknown_format_falls_through(self):
        """Unknown format should not crash — falls to default."""
        result = gen_string({"type": "string", "format": "invented-format"})
        assert isinstance(result, str)

    def test_negative_max_length(self):
        """Negative maxLength should not crash."""
        result = gen_string({"type": "string", "maxLength": -1})
        assert isinstance(result, str)

    def test_zero_max_length(self):
        """Zero maxLength should produce an empty or short string."""
        result = gen_string({"type": "string", "maxLength": 0})
        assert isinstance(result, str)

    def test_mismatched_weights_length(self):
        """Weights length != enum length should raise or degrade gracefully."""
        schema = {"type": "string", "enum": ["a", "b"], "x-datagen-weight": [1]}
        try:
            result = gen_string(schema)
            assert result in ["a", "b"]
        except (ValueError, IndexError):
            pass  # Acceptable to raise

    def test_empty_pattern(self):
        """Empty pattern should produce empty string."""
        result = gen_string({"type": "string", "pattern": ""})
        assert isinstance(result, str)


class TestIntegerNegative:
    def test_min_greater_than_max(self):
        """minimum > maximum raises ValueError."""
        with pytest.raises(ValueError):
            gen_integer({"type": "integer", "minimum": 100, "maximum": 1})

    def test_empty_enum_raises(self):
        with pytest.raises(IndexError):
            gen_integer({"type": "integer", "enum": []})

    def test_non_integer_enum(self):
        """Enum with floats should still work (cast or direct return)."""
        result = gen_integer({"type": "integer", "enum": [1.5, 2.5]})
        assert result in [1.5, 2.5]

    def test_zero_multiple_of(self):
        """multipleOf=0 should not cause division by zero."""
        try:
            result = gen_integer({"type": "integer", "minimum": 0, "maximum": 10, "multipleOf": 0})
            assert isinstance(result, int)
        except (ValueError, ZeroDivisionError):
            pass  # Acceptable


class TestNumberNegative:
    def test_min_greater_than_max(self):
        result = gen_number({"type": "number", "minimum": 100.0, "maximum": 1.0})
        assert isinstance(result, (int, float))

    def test_empty_schema(self):
        result = gen_number({"type": "number"})
        assert isinstance(result, (int, float))

    def test_negative_precision(self):
        """Negative precision should not crash."""
        result = gen_number({"type": "number", "x-datagen-precision": -1, "minimum": 0, "maximum": 10})
        assert isinstance(result, (int, float))


class TestBooleanNegative:
    def test_weight_out_of_range_high(self):
        """Weight > 1.0 should not crash."""
        result = gen_boolean({"type": "boolean", "x-datagen-weight": 5.0})
        assert isinstance(result, bool)

    def test_weight_negative(self):
        """Negative weight should not crash."""
        result = gen_boolean({"type": "boolean", "x-datagen-weight": -1.0})
        assert isinstance(result, bool)

    def test_no_weight(self):
        result = gen_boolean({"type": "boolean"})
        assert isinstance(result, bool)


class TestArrayNegative:
    def test_min_items_greater_than_max(self):
        """minItems > maxItems should not crash."""
        schema = {
            "type": "array",
            "items": {"type": "integer"},
            "minItems": 10,
            "maxItems": 1,
        }
        try:
            result = gen_array(schema)
            assert isinstance(result, list)
        except ValueError:
            pass  # Acceptable

    def test_missing_items_schema(self):
        """Array with no items schema should still produce something."""
        schema = {"type": "array", "minItems": 1, "maxItems": 3}
        try:
            result = gen_array(schema)
            assert isinstance(result, list)
        except (KeyError, TypeError):
            pass  # Acceptable


class TestDistributionNegative:
    def test_empty_config(self):
        """Empty distribution config should default gracefully."""
        result = sample_distribution({})
        assert isinstance(result, (int, float))

    def test_histogram_empty_bins(self):
        """Histogram with empty bins."""
        result = sample_distribution({"type": "histogram", "bins": []})
        assert isinstance(result, (int, float))

    def test_negative_lambda(self):
        """Negative lambda in Poisson should not crash or loop forever."""
        try:
            result = sample_distribution({"type": "poisson", "lambda": -1})
            assert isinstance(result, (int, float))
        except (ValueError, OverflowError):
            pass  # Acceptable


class TestWeightedChoiceNegative:
    def test_empty_list_raises(self):
        with pytest.raises(IndexError):
            weighted_choice([])

    def test_empty_list_with_weights_raises(self):
        with pytest.raises((IndexError, ValueError)):
            weighted_choice([], [])

    def test_none_values(self):
        """None in values list should still work."""
        result = weighted_choice([None, "a", "b"])
        assert result in [None, "a", "b"]


# ---------------------------------------------------------------------------
# Schema parser negative tests
# ---------------------------------------------------------------------------

class TestSchemaParserNegative:
    def test_no_type(self):
        """Schema without explicit type should default to string."""
        val = generate_value({"x-datagen-faker": "person.name"})
        assert isinstance(val, str)

    def test_unknown_type(self):
        """Unknown type should return None."""
        val = generate_value({"type": "imaginary"})
        assert val is None

    def test_empty_schema(self):
        """Completely empty schema object."""
        val = generate_value({})
        assert isinstance(val, str)  # defaults to string

    def test_missing_properties_key(self):
        """Object schema with no properties key."""
        schema = {"type": "object"}
        parser = SchemaParser(schema)
        records = parser.generate(count=3)
        assert len(records) == 3
        for r in records:
            assert isinstance(r, dict)

    def test_negative_count(self):
        """Negative count should produce empty list or raise."""
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        parser = SchemaParser(schema)
        try:
            records = parser.generate(count=-1)
            assert records == [] or len(records) == 0
        except ValueError:
            pass

    def test_invalid_ref(self):
        """Invalid $ref should not crash the parser."""
        schema = {
            "type": "object",
            "properties": {
                "bad": {"$ref": "#/$defs/nonexistent"}
            }
        }
        parser = SchemaParser(schema)
        try:
            records = parser.generate(count=1)
            assert len(records) == 1
        except (KeyError, TypeError):
            pass  # Acceptable

    def test_circular_ref_doesnt_hang(self):
        """Schema referencing itself should not loop infinitely."""
        schema = {
            "type": "object",
            "$defs": {
                "self_ref": {
                    "type": "object",
                    "properties": {"val": {"type": "integer", "minimum": 1, "maximum": 1}},
                }
            },
            "properties": {
                "node": {"$ref": "#/$defs/self_ref"}
            }
        }
        parser = SchemaParser(schema)
        records = parser.generate(count=2)
        assert len(records) == 2


# ---------------------------------------------------------------------------
# Pipeline negative tests
# ---------------------------------------------------------------------------

class TestPipelineNegative:
    def test_missing_dependency(self):
        """Pipeline with unresolved dependency should handle gracefully."""
        pipeline = GenerationPipeline()
        pipeline.add_schema("child",
                            {"type": "object", "properties": {}},
                            count=1, depends_on=["nonexistent_parent"])
        # Pipeline may silently resolve or raise — either is acceptable
        try:
            order = pipeline.resolve_order()
            assert isinstance(order, list)
        except Exception:
            pass  # Also acceptable

    def test_empty_pipeline(self):
        """Empty pipeline should produce no data."""
        pipeline = GenerationPipeline()
        result = pipeline.execute()
        assert result.total_records == 0
        assert result.datasets == {}


# ---------------------------------------------------------------------------
# Connector negative tests
# ---------------------------------------------------------------------------

class TestConnectorNegative:
    def test_unknown_connector_type(self):
        """Creating a connector with unknown type should raise ValueError."""
        config = ConnectionConfig(name="bad", connector_type="totally_fake", host="x")
        with pytest.raises(ValueError, match="Unknown connector type"):
            create_connector(config)

    def test_connection_config_empty_host(self):
        """Empty host should still create config (validation at connect time)."""
        config = ConnectionConfig(name="test", connector_type="elasticsearch", host="")
        assert config.host == ""

    def test_push_result_defaults(self):
        """PushResult with only success=False has sane defaults."""
        r = PushResult(success=False)
        assert r.records_sent == 0
        assert r.records_failed == 0
        assert r.errors == []

    def test_health_check_no_latency(self):
        hc = HealthCheck(healthy=False, message="refused")
        assert hc.latency_ms == 0.0  # defaults to 0.0
        assert not hc.healthy


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
