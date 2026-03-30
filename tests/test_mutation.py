"""Mutation tests — verify that changing schema inputs changes outputs.

These tests ensure the generators actually *use* the constraints provided.
If a mutation (change to schema) doesn't affect the output, the generator
is likely ignoring that field.
"""

import statistics

import pytest

from datagen.engine.generators import (
    gen_string, gen_integer, gen_number, gen_boolean,
    gen_array, sample_distribution, weighted_choice,
)
from datagen.engine.schema_parser import SchemaParser, generate_value


# ---------------------------------------------------------------------------
# String mutations
# ---------------------------------------------------------------------------

class TestStringMutations:
    def test_enum_change_changes_output(self):
        """Changing the enum set should change what values can appear."""
        schema_a = {"type": "string", "enum": ["alpha"]}
        schema_b = {"type": "string", "enum": ["beta"]}
        assert gen_string(schema_a) == "alpha"
        assert gen_string(schema_b) == "beta"

    def test_format_email_vs_uuid(self):
        """Different formats produce structurally different strings."""
        email = gen_string({"type": "string", "format": "email"})
        uid = gen_string({"type": "string", "format": "uuid"})
        assert "@" in email
        assert "-" in uid and len(uid) == 36

    def test_faker_name_vs_company(self):
        """Different faker providers produce different distributions."""
        names = {gen_string({"type": "string", "x-datagen-faker": "person.name"}) for _ in range(20)}
        companies = {gen_string({"type": "string", "x-datagen-faker": "company.name"}) for _ in range(20)}
        # Very unlikely to have identical sets
        assert names != companies

    def test_pattern_change(self):
        """Different patterns produce different output structures."""
        a = gen_string({"type": "string", "pattern": "INC[0-9]{7}"})
        b = gen_string({"type": "string", "pattern": "CHG[0-9]{7}"})
        assert a[:3] == "INC"
        assert b[:3] == "CHG"

    def test_max_length_mutation(self):
        """Reducing maxLength should produce shorter strings."""
        short_results = [gen_string({"type": "string", "maxLength": 10}) for _ in range(20)]
        long_results = [gen_string({"type": "string", "maxLength": 200}) for _ in range(20)]
        avg_short = statistics.mean(len(s) for s in short_results)
        avg_long = statistics.mean(len(s) for s in long_results)
        assert avg_short <= avg_long


# ---------------------------------------------------------------------------
# Integer mutations
# ---------------------------------------------------------------------------

class TestIntegerMutations:
    def test_range_shift(self):
        """Shifting the range should shift the output."""
        low = [gen_integer({"type": "integer", "minimum": 0, "maximum": 10}) for _ in range(50)]
        high = [gen_integer({"type": "integer", "minimum": 90, "maximum": 100}) for _ in range(50)]
        assert statistics.mean(low) < statistics.mean(high)

    def test_enum_mutation(self):
        """Changing enum values changes output."""
        a = gen_integer({"type": "integer", "enum": [1]})
        b = gen_integer({"type": "integer", "enum": [999]})
        assert a == 1
        assert b == 999

    def test_multiple_of_mutation(self):
        """Different multipleOf produces different value sets."""
        twos = {gen_integer({"type": "integer", "minimum": 0, "maximum": 20, "multipleOf": 2}) for _ in range(50)}
        fives = {gen_integer({"type": "integer", "minimum": 0, "maximum": 20, "multipleOf": 5}) for _ in range(50)}
        # All multiples of 2 should be even
        assert all(v % 2 == 0 for v in twos)
        assert all(v % 5 == 0 for v in fives)

    def test_distribution_mutation(self):
        """Gaussian with different means should produce different averages."""
        low_mean = [gen_integer({"type": "integer", "x-datagen-distribution": {"type": "gaussian", "mean": 10, "stddev": 2}}) for _ in range(100)]
        high_mean = [gen_integer({"type": "integer", "x-datagen-distribution": {"type": "gaussian", "mean": 90, "stddev": 2}}) for _ in range(100)]
        assert statistics.mean(low_mean) < statistics.mean(high_mean)


# ---------------------------------------------------------------------------
# Number mutations
# ---------------------------------------------------------------------------

class TestNumberMutations:
    def test_precision_mutation(self):
        """Higher precision allows more decimal places."""
        low_prec = [gen_number({"type": "number", "x-datagen-precision": 1, "minimum": 0, "maximum": 100}) for _ in range(20)]
        high_prec = [gen_number({"type": "number", "x-datagen-precision": 6, "minimum": 0, "maximum": 100}) for _ in range(20)]
        avg_decimals_low = statistics.mean(len(str(v).split(".")[-1]) if "." in str(v) else 0 for v in low_prec)
        avg_decimals_high = statistics.mean(len(str(v).split(".")[-1]) if "." in str(v) else 0 for v in high_prec)
        assert avg_decimals_low <= avg_decimals_high

    def test_range_mutation(self):
        low = [gen_number({"type": "number", "minimum": 0, "maximum": 1}) for _ in range(50)]
        high = [gen_number({"type": "number", "minimum": 999, "maximum": 1000}) for _ in range(50)]
        assert statistics.mean(low) < statistics.mean(high)


# ---------------------------------------------------------------------------
# Boolean mutations
# ---------------------------------------------------------------------------

class TestBooleanMutations:
    def test_weight_mutation(self):
        """Changing weight should shift the true/false ratio."""
        high_true = [gen_boolean({"type": "boolean", "x-datagen-weight": 0.95}) for _ in range(200)]
        low_true = [gen_boolean({"type": "boolean", "x-datagen-weight": 0.05}) for _ in range(200)]
        assert sum(high_true) > sum(low_true)


# ---------------------------------------------------------------------------
# Array mutations
# ---------------------------------------------------------------------------

class TestArrayMutations:
    def test_size_mutation(self):
        """Changing minItems/maxItems should change array lengths."""
        small = [gen_array({"type": "array", "items": {"type": "integer"}, "minItems": 1, "maxItems": 2}) for _ in range(20)]
        large = [gen_array({"type": "array", "items": {"type": "integer"}, "minItems": 8, "maxItems": 10}) for _ in range(20)]
        assert statistics.mean(len(a) for a in small) < statistics.mean(len(a) for a in large)

    def test_items_type_mutation(self):
        """Changing items type should change element types."""
        int_arr = gen_array({"type": "array", "items": {"type": "integer"}, "minItems": 3, "maxItems": 3})
        str_arr = gen_array({"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3})
        assert all(isinstance(v, int) for v in int_arr)
        assert all(isinstance(v, str) for v in str_arr)


# ---------------------------------------------------------------------------
# Schema parser mutations
# ---------------------------------------------------------------------------

class TestSchemaParserMutations:
    def test_adding_field_increases_keys(self):
        """Adding a field to the schema should add it to output records."""
        schema1 = {"type": "object", "properties": {"a": {"type": "integer"}}}
        schema2 = {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "string"}}}
        r1 = SchemaParser(schema1).generate(count=1)[0]
        r2 = SchemaParser(schema2).generate(count=1)[0]
        assert "b" not in r1
        assert "b" in r2

    def test_removing_field_decreases_keys(self):
        """Removing a field should remove it from output."""
        schema = {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "string"}}}
        r = SchemaParser(schema).generate(count=1)[0]
        assert "a" in r and "b" in r

        schema_reduced = {"type": "object", "properties": {"a": {"type": "integer"}}}
        r2 = SchemaParser(schema_reduced).generate(count=1)[0]
        assert "a" in r2
        assert "b" not in r2

    def test_null_rate_mutation(self):
        """Setting null rate to 1.0 should make field always null."""
        schema_no_null = {"type": "object", "properties": {"v": {"type": "string", "x-datagen-faker": "person.name", "x-datagen-null-rate": 0.0}}}
        schema_all_null = {"type": "object", "properties": {"v": {"type": "string", "x-datagen-faker": "person.name", "x-datagen-null-rate": 1.0}}}
        records_no = SchemaParser(schema_no_null).generate(count=20)
        records_all = SchemaParser(schema_all_null).generate(count=20)
        assert all(r["v"] is not None for r in records_no)
        assert all(r["v"] is None for r in records_all)

    def test_unique_constraint_mutation(self):
        """Adding x-datagen-unique should force unique values."""
        schema_dup = {"type": "object", "properties": {"id": {"type": "integer", "minimum": 1, "maximum": 3}}}
        schema_uniq = {"type": "object", "properties": {"id": {"type": "string", "format": "uuid", "x-datagen-unique": True}}}
        dup_ids = [r["id"] for r in SchemaParser(schema_dup).generate(count=100)]
        uniq_ids = [r["id"] for r in SchemaParser(schema_uniq).generate(count=100)]
        # Duplicate IDs likely in constrained range
        assert len(set(dup_ids)) < len(dup_ids)
        # Unique IDs must all be distinct
        assert len(set(uniq_ids)) == 100

    def test_dependency_mutation(self):
        """Adding dependency should constrain state based on priority."""
        schema_free = {
            "type": "object",
            "properties": {
                "priority": {"type": "integer", "enum": [1]},
                "state": {"type": "integer", "enum": [1, 2, 3, 6, 7]},
            }
        }
        schema_dep = {
            "type": "object",
            "properties": {
                "priority": {"type": "integer", "enum": [1]},
                "state": {
                    "type": "integer",
                    "enum": [1, 2, 3, 6, 7],
                    "x-datagen-depends-on": {
                        "field": "priority",
                        "rules": {"1": {"enum": [1, 2]}}
                    }
                },
            }
        }
        free_states = {r["state"] for r in SchemaParser(schema_free).generate(count=100)}
        dep_states = {r["state"] for r in SchemaParser(schema_dep).generate(count=100)}
        assert len(free_states) > len(dep_states)
        assert dep_states.issubset({1, 2})


# ---------------------------------------------------------------------------
# Distribution mutations
# ---------------------------------------------------------------------------

class TestDistributionMutations:
    def test_gaussian_mean_mutation(self):
        """Different mean should shift output."""
        low = [sample_distribution({"type": "gaussian", "mean": 10, "stddev": 1}) for _ in range(100)]
        high = [sample_distribution({"type": "gaussian", "mean": 90, "stddev": 1}) for _ in range(100)]
        assert statistics.mean(low) < statistics.mean(high)

    def test_uniform_range_mutation(self):
        """Different range should change output bounds."""
        narrow = [sample_distribution({"type": "uniform", "min": 0, "max": 1}) for _ in range(50)]
        wide = [sample_distribution({"type": "uniform", "min": 0, "max": 1000}) for _ in range(50)]
        assert max(narrow) <= 1.0
        assert statistics.mean(wide) > statistics.mean(narrow)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
