"""Property-based tests for GenForge data generators using Hypothesis.

These tests verify invariants that must hold for *all* valid inputs,
not just hand-picked examples.
"""

import math
import re
import string
import uuid

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from datagen.engine.generators import (
    gen_string,
    gen_integer,
    gen_number,
    gen_boolean,
    gen_datetime,
    gen_array,
    sample_distribution,
    weighted_choice,
    _gen_from_pattern,
    _sample_char_class,
)
from datagen.engine.schema_parser import SchemaParser, generate_value, generate_record


# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------

enum_values_st = st.lists(
    st.one_of(st.text(min_size=1, max_size=30), st.integers(-1000, 1000)),
    min_size=1,
    max_size=10,
    unique=True,
)

weight_list_st = st.lists(
    st.integers(min_value=1, max_value=100),
    min_size=1,
    max_size=10,
)


# ---------------------------------------------------------------------------
# weighted_choice properties
# ---------------------------------------------------------------------------

class TestWeightedChoiceProperties:
    @given(values=st.lists(st.integers(), min_size=1, max_size=20))
    def test_result_always_in_values(self, values):
        """weighted_choice must always return an element from the input list."""
        result = weighted_choice(values)
        assert result in values

    @given(
        values=st.lists(st.text(min_size=1, max_size=10), min_size=2, max_size=10, unique=True),
        data=st.data(),
    )
    def test_weighted_result_in_values(self, values, data):
        """weighted_choice with explicit weights must return an element from values."""
        weights = data.draw(st.lists(
            st.integers(min_value=1, max_value=100),
            min_size=len(values),
            max_size=len(values),
        ))
        result = weighted_choice(values, weights)
        assert result in values

    @given(st.integers(min_value=-1000, max_value=1000))
    def test_single_element(self, val):
        """A single-element list always returns that element."""
        assert weighted_choice([val]) == val


# ---------------------------------------------------------------------------
# String generator properties
# ---------------------------------------------------------------------------

class TestStringGeneratorProperties:
    @given(st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=8, unique=True))
    def test_enum_always_in_set(self, enum_vals):
        """gen_string with enum must return a member of the enum."""
        schema = {"type": "string", "enum": enum_vals}
        for _ in range(5):
            assert gen_string(schema) in enum_vals

    @given(
        min_len=st.integers(min_value=1, max_value=20),
        max_len=st.integers(min_value=20, max_value=200),
    )
    def test_length_bounds(self, min_len, max_len):
        """gen_string respects maxLength."""
        schema = {"type": "string", "minLength": min_len, "maxLength": max_len}
        result = gen_string(schema)
        assert isinstance(result, str)
        assert len(result) <= max_len

    @given(st.sampled_from([
        "person.name", "internet.email", "company.name", "lorem.sentence",
        "lorem.word", "address.city", "job.title",
    ]))
    def test_faker_returns_nonempty_string(self, faker_key):
        """All supported Faker providers produce non-empty strings."""
        schema = {"type": "string", "x-datagen-faker": faker_key}
        result = gen_string(schema)
        assert isinstance(result, str)
        assert len(result) > 0

    @given(st.sampled_from(["email", "uuid", "ipv4", "date-time", "date"]))
    def test_format_returns_string(self, fmt):
        """All format generators return a non-empty string."""
        result = gen_string({"type": "string", "format": fmt})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_uuid_format_is_valid(self):
        """UUID format must produce a valid UUID."""
        for _ in range(20):
            result = gen_string({"type": "string", "format": "uuid"})
            uuid.UUID(result)  # Raises if invalid

    def test_email_format_has_at(self):
        """Email format must contain '@'."""
        for _ in range(20):
            result = gen_string({"type": "string", "format": "email"})
            assert "@" in result

    def test_ipv4_format_has_four_octets(self):
        """IPv4 format must have 4 dot-separated octets."""
        for _ in range(20):
            result = gen_string({"type": "string", "format": "ipv4"})
            parts = result.split(".")
            assert len(parts) == 4
            for p in parts:
                assert 0 <= int(p) <= 255


# ---------------------------------------------------------------------------
# Integer generator properties
# ---------------------------------------------------------------------------

class TestIntegerGeneratorProperties:
    @given(
        lo=st.integers(min_value=-1000, max_value=0),
        hi=st.integers(min_value=1, max_value=1000),
    )
    def test_range_respected(self, lo, hi):
        """gen_integer must stay within [minimum, maximum]."""
        schema = {"type": "integer", "minimum": lo, "maximum": hi}
        for _ in range(10):
            val = gen_integer(schema)
            assert lo <= val <= hi

    @given(st.lists(st.integers(-100, 100), min_size=1, max_size=10, unique=True))
    def test_enum_respected(self, enum_vals):
        """gen_integer with enum must return a member."""
        schema = {"type": "integer", "enum": enum_vals}
        for _ in range(10):
            assert gen_integer(schema) in enum_vals

    @given(
        lo=st.integers(0, 50),
        hi=st.integers(51, 200),
        step=st.sampled_from([1, 2, 5, 10]),
    )
    def test_multiple_of(self, lo, hi, step):
        """multipleOf produces values where (val - minimum) is divisible by step."""
        schema = {"type": "integer", "minimum": lo, "maximum": hi, "multipleOf": step}
        for _ in range(10):
            val = gen_integer(schema)
            assert lo <= val <= hi
            assert (val - lo) % step == 0


# ---------------------------------------------------------------------------
# Number generator properties
# ---------------------------------------------------------------------------

class TestNumberGeneratorProperties:
    @given(
        lo=st.floats(min_value=-1000, max_value=0, allow_nan=False, allow_infinity=False),
        hi=st.floats(min_value=1, max_value=1000, allow_nan=False, allow_infinity=False),
    )
    def test_range_respected(self, lo, hi):
        """gen_number must stay within [minimum, maximum]."""
        schema = {"type": "number", "minimum": lo, "maximum": hi}
        for _ in range(5):
            val = gen_number(schema)
            assert lo <= val <= hi

    @given(st.integers(min_value=1, max_value=6))
    def test_precision(self, prec):
        """x-datagen-precision limits decimal places (prec >= 1)."""
        schema = {"type": "number", "x-datagen-precision": prec,
                  "minimum": 0, "maximum": 100}
        val = gen_number(schema)
        # Check decimal places
        s = str(val)
        if "." in s:
            assert len(s.split(".")[-1]) <= prec


# ---------------------------------------------------------------------------
# Boolean generator properties
# ---------------------------------------------------------------------------

class TestBooleanGeneratorProperties:
    @given(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    def test_always_returns_bool(self, weight):
        """gen_boolean always returns a bool regardless of weight."""
        schema = {"type": "boolean", "x-datagen-weight": weight}
        assert isinstance(gen_boolean(schema), bool)

    def test_extreme_weight_true(self):
        """Weight of 1.0 should almost always produce True."""
        schema = {"type": "boolean", "x-datagen-weight": 1.0}
        results = [gen_boolean(schema) for _ in range(100)]
        assert all(results)

    def test_extreme_weight_false(self):
        """Weight of 0.0 should almost always produce False."""
        schema = {"type": "boolean", "x-datagen-weight": 0.0}
        results = [gen_boolean(schema) for _ in range(100)]
        assert not any(results)


# ---------------------------------------------------------------------------
# Distribution properties
# ---------------------------------------------------------------------------

class TestDistributionProperties:
    @given(
        lo=st.floats(min_value=-100, max_value=0, allow_nan=False, allow_infinity=False),
        hi=st.floats(min_value=1, max_value=100, allow_nan=False, allow_infinity=False),
    )
    def test_uniform_in_range(self, lo, hi):
        """Uniform distribution stays within [min, max]."""
        val = sample_distribution({"type": "uniform", "min": lo, "max": hi})
        assert lo <= val <= hi

    @given(st.floats(min_value=0.1, max_value=50, allow_nan=False, allow_infinity=False))
    def test_poisson_nonnegative(self, lam):
        """Poisson distribution always produces non-negative values."""
        val = sample_distribution({"type": "poisson", "lambda": lam})
        assert val >= 0

    @given(st.floats(min_value=0.1, max_value=100, allow_nan=False, allow_infinity=False))
    def test_exponential_positive(self, mean):
        """Exponential distribution always produces positive values."""
        val = sample_distribution({"type": "exponential", "mean": mean})
        assert val > 0


# ---------------------------------------------------------------------------
# Pattern generator properties
# ---------------------------------------------------------------------------

class TestPatternProperties:
    @given(st.sampled_from([
        "INC[0-9]{7}",
        "CHG[0-9]{7}",
        "PRB[0-9]{7}",
        "REQ[0-9]{7}",
        "KB[0-9]{7}",
        "ASSET[0-9]{6}",
        "CVE-202[4-6]-[0-9]{5}",
    ]))
    def test_known_patterns_produce_valid_strings(self, pattern):
        """Known ServiceNow-style patterns must produce non-empty strings."""
        result = _gen_from_pattern(pattern)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_inc_pattern_structure(self):
        """INC pattern must produce 'INC' + 7 digits."""
        for _ in range(20):
            result = _gen_from_pattern("INC[0-9]{7}")
            assert result.startswith("INC")
            assert len(result) == 10
            assert result[3:].isdigit()


# ---------------------------------------------------------------------------
# SchemaParser properties
# ---------------------------------------------------------------------------

class TestSchemaParserProperties:
    @given(count=st.integers(min_value=1, max_value=50))
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_generate_count(self, count):
        """SchemaParser.generate always returns exactly `count` records."""
        schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "value": {"type": "integer", "minimum": 0, "maximum": 100},
            }
        }
        parser = SchemaParser(schema)
        records = parser.generate(count=count)
        assert len(records) == count

    @given(count=st.integers(min_value=1, max_value=20))
    @settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
    def test_all_properties_present(self, count):
        """Every generated record must contain all declared properties."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "x-datagen-faker": "person.name"},
                "age": {"type": "integer", "minimum": 0, "maximum": 120},
                "active": {"type": "boolean"},
                "email": {"type": "string", "format": "email"},
            }
        }
        parser = SchemaParser(schema)
        for rec in parser.generate(count=count):
            assert set(rec.keys()) == {"name", "age", "active", "email"}
            assert isinstance(rec["name"], str)
            assert isinstance(rec["age"], int)
            assert isinstance(rec["active"], bool)
            assert "@" in rec["email"]

    @given(count=st.integers(min_value=2, max_value=30))
    @settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
    def test_unique_constraint(self, count):
        """x-datagen-unique fields must have unique values across all records."""
        schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string", "format": "uuid", "x-datagen-unique": True},
            }
        }
        parser = SchemaParser(schema)
        records = parser.generate(count=count)
        ids = [r["id"] for r in records]
        assert len(set(ids)) == count

    @settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
    @given(null_rate=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    def test_null_rate_produces_nulls_or_values(self, null_rate):
        """With x-datagen-null-rate, values are either None or a valid string."""
        schema = {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "x-datagen-faker": "lorem.word",
                    "x-datagen-null-rate": null_rate,
                }
            }
        }
        parser = SchemaParser(schema)
        records = parser.generate(count=50)
        for r in records:
            val = r["field"]
            assert val is None or isinstance(val, str)


# ---------------------------------------------------------------------------
# generate_value properties
# ---------------------------------------------------------------------------

class TestGenerateValueProperties:
    @given(st.sampled_from(["string", "integer", "number", "boolean"]))
    def test_type_respected(self, schema_type):
        """generate_value returns the correct Python type."""
        expected = {"string": str, "integer": int, "number": float, "boolean": bool}
        schema = {"type": schema_type}
        val = generate_value(schema)
        assert isinstance(val, expected[schema_type])

    @given(
        values=st.lists(st.integers(-100, 100), min_size=1, max_size=10, unique=True),
        data=st.data(),
    )
    def test_enum_via_generate_value(self, values, data):
        """generate_value with enum always picks from the enum set."""
        weights = data.draw(st.lists(
            st.integers(1, 50),
            min_size=len(values),
            max_size=len(values),
        ))
        schema = {"type": "integer", "enum": values, "x-datagen-weight": weights}
        for _ in range(5):
            assert generate_value(schema) in values

    def test_const(self):
        """const always returns the constant value."""
        for val in [42, "fixed", True, None]:
            assert generate_value({"const": val}) == val


# ---------------------------------------------------------------------------
# Array generator properties
# ---------------------------------------------------------------------------

class TestArrayGeneratorProperties:
    @given(
        min_items=st.integers(min_value=0, max_value=3),
        max_items=st.integers(min_value=3, max_value=10),
    )
    def test_array_length_bounds(self, min_items, max_items):
        """gen_array respects minItems and maxItems."""
        schema = {
            "type": "array",
            "items": {"type": "integer", "minimum": 0, "maximum": 100},
            "minItems": min_items,
            "maxItems": max_items,
        }
        result = gen_array(schema)
        assert min_items <= len(result) <= max_items

    @given(st.integers(min_value=1, max_value=8))
    def test_unique_items(self, count):
        """uniqueItems produces all-distinct values."""
        schema = {
            "type": "array",
            "items": {"type": "string", "format": "uuid"},
            "minItems": count,
            "maxItems": count,
            "uniqueItems": True,
        }
        result = gen_array(schema)
        assert len(result) == len(set(result))


# ---------------------------------------------------------------------------
# Deep merge / ref resolution properties
# ---------------------------------------------------------------------------

class TestRefResolutionProperties:
    @given(count=st.integers(min_value=1, max_value=10))
    @settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
    def test_ref_resolution_produces_valid_records(self, count):
        """$ref resolution must produce records with the referenced schema's fields."""
        schema = {
            "type": "object",
            "$defs": {
                "addr": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "x-datagen-faker": "address.city"},
                    }
                }
            },
            "properties": {
                "home": {"$ref": "#/$defs/addr"},
            }
        }
        parser = SchemaParser(schema)
        records = parser.generate(count=count)
        assert len(records) == count
        for r in records:
            assert "city" in r["home"]
            assert isinstance(r["home"]["city"], str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
