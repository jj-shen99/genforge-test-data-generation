"""Extended property-based tests using Hypothesis.

Covers: enrichment invariants, pipeline properties, timeseries properties,
and cross-generator consistency checks.
"""

import re
import uuid

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from datagen.engine.generators import (
    gen_string, gen_integer, gen_number, gen_boolean,
    gen_array, gen_datetime, sample_distribution, weighted_choice,
    FAKER_PROVIDERS,
)
from datagen.engine.schema_parser import SchemaParser, generate_value, generate_record
from datagen.engine.timeseries import TimeSeriesGenerator, generate_log_entries
from datagen.engine.pipeline import GenerationPipeline
from datagen.api.server import _enrich_extracted_schema


# ---------------------------------------------------------------------------
# Enrichment invariants
# ---------------------------------------------------------------------------

class TestEnrichmentProperties:
    @given(st.sampled_from([
        "name", "first_name", "last_name", "email", "phone", "city",
        "state", "country", "company", "url", "ip_address",
        "description", "priority", "severity", "impact", "urgency",
        "state", "category", "active", "number", "location",
        "assigned_to", "opened_by", "domain", "user_agent",
    ]))
    def test_known_fields_always_enriched(self, field_name):
        """Known field names should always get some enrichment."""
        schema = {"type": "object", "properties": {
            field_name: {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        prop = result["properties"][field_name]
        has_hint = any(k in prop for k in ("x-datagen-faker", "enum", "pattern", "format"))
        assert has_hint, f"Field '{field_name}' was not enriched"

    @given(st.text(
        alphabet=st.characters(whitelist_categories=("Ll",), min_codepoint=97, max_codepoint=122),
        min_size=10, max_size=30,
    ))
    def test_random_field_names_dont_crash(self, field_name):
        """Random field names should never crash the enrichment function."""
        schema = {"type": "object", "properties": {
            field_name: {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert "properties" in result

    @given(st.sampled_from(["integer", "number", "boolean"]))
    def test_non_string_types_never_enriched(self, type_name):
        """Non-string type fields named 'priority' etc. should NOT be enriched."""
        schema = {"type": "object", "properties": {
            "priority": {"type": type_name},
        }}
        result = _enrich_extracted_schema(schema)
        prop = result["properties"]["priority"]
        assert "x-datagen-faker" not in prop
        assert "enum" not in prop

    def test_enrichment_idempotent(self):
        """Enriching an already-enriched schema should not change it further."""
        schema = {"type": "object", "properties": {
            "name": {"type": "string"},
            "priority": {"type": "string"},
            "email": {"type": "string"},
        }}
        first = _enrich_extracted_schema(schema)
        import copy
        second = _enrich_extracted_schema(copy.deepcopy(first))
        assert first == second

    @given(st.sampled_from(list(FAKER_PROVIDERS.keys())))
    def test_all_faker_providers_produce_strings(self, key):
        """Every registered FAKER_PROVIDER must produce a non-empty string."""
        result = FAKER_PROVIDERS[key]()
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Pipeline properties
# ---------------------------------------------------------------------------

class TestPipelineProperties:
    @given(
        user_count=st.integers(min_value=1, max_value=20),
        order_count=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
    def test_referential_integrity(self, user_count, order_count):
        """Orders must always reference existing user IDs."""
        pipeline = GenerationPipeline()
        pipeline.add_schema(
            "users",
            {"type": "object", "properties": {
                "id": {"type": "string", "format": "uuid", "x-datagen-unique": True},
                "name": {"type": "string", "x-datagen-faker": "person.name"},
            }},
            count=user_count,
            ref_tracking={"id": "user.id"},
        )
        pipeline.add_schema(
            "orders",
            {"type": "object", "properties": {
                "id": {"type": "string", "format": "uuid"},
                "user_id": {"type": "string", "x-datagen-ref": "user.id"},
                "amount": {"type": "number", "minimum": 1, "maximum": 100},
            }},
            count=order_count,
            depends_on=["users"],
        )
        result = pipeline.execute()
        assert result.total_records == user_count + order_count
        user_ids = {u["id"] for u in result.datasets["users"]}
        for order in result.datasets["orders"]:
            assert order["user_id"] in user_ids

    @given(count=st.integers(min_value=1, max_value=30))
    @settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
    def test_pipeline_total_records(self, count):
        """Pipeline total_records should match sum of all dataset counts."""
        pipeline = GenerationPipeline()
        pipeline.add_schema(
            "data",
            {"type": "object", "properties": {"v": {"type": "integer"}}},
            count=count,
        )
        result = pipeline.execute()
        assert result.total_records == count
        assert len(result.datasets["data"]) == count


# ---------------------------------------------------------------------------
# TimeSeries properties
# ---------------------------------------------------------------------------

class TestTimeSeriesProperties:
    @given(st.sampled_from(["sine", "random_walk", "seasonal", "spiky"]))
    @settings(max_examples=4, suppress_health_check=[HealthCheck.too_slow])
    def test_pattern_produces_points(self, pattern):
        """All time-series patterns should produce at least one data point."""
        gen = TimeSeriesGenerator({
            "pattern": pattern,
            "start": "now-1h",
            "end": "now",
            "interval_seconds": 60,
        })
        points = gen.generate()
        assert len(points) > 0
        assert all("value" in p and "timestamp" in p for p in points)

    @given(count=st.integers(min_value=1, max_value=100))
    @settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
    def test_log_entry_count(self, count):
        """generate_log_entries should produce exactly `count` entries."""
        logs = generate_log_entries({"count": count, "start": "now-1h"})
        assert len(logs) == count

    def test_log_entries_have_required_fields(self):
        """Log entries must have timestamp, level, message, source."""
        logs = generate_log_entries({"count": 20, "start": "now-1h"})
        for log in logs:
            assert "timestamp" in log
            assert "level" in log
            assert "message" in log
            assert log["level"] in {"DEBUG", "INFO", "WARN", "ERROR"}


# ---------------------------------------------------------------------------
# Cross-generator consistency
# ---------------------------------------------------------------------------

class TestCrossGeneratorConsistency:
    @given(st.sampled_from(["string", "integer", "number", "boolean"]))
    def test_generate_value_type_matches(self, type_name):
        """generate_value should return the correct Python type."""
        expected = {"string": str, "integer": int, "number": float, "boolean": bool}
        val = generate_value({"type": type_name})
        assert isinstance(val, expected[type_name])

    @given(
        min_val=st.integers(min_value=0, max_value=50),
        max_val=st.integers(min_value=51, max_value=100),
    )
    def test_integer_generate_value_in_range(self, min_val, max_val):
        """generate_value for integer with bounds should respect them."""
        schema = {"type": "integer", "minimum": min_val, "maximum": max_val}
        for _ in range(10):
            val = generate_value(schema)
            assert min_val <= val <= max_val

    @given(st.sampled_from(["email", "uuid", "ipv4", "date-time", "date"]))
    def test_string_formats_via_generate_value(self, fmt):
        """generate_value for string formats should produce valid strings."""
        val = generate_value({"type": "string", "format": fmt})
        assert isinstance(val, str)
        assert len(val) > 0

    def test_record_and_parser_equivalent(self):
        """generate_record and SchemaParser.generate should produce compatible output."""
        schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "val": {"type": "integer", "minimum": 1, "maximum": 100},
            }
        }
        direct = generate_record(schema)
        parsed = SchemaParser(schema).generate(count=1)[0]
        assert set(direct.keys()) == set(parsed.keys())
        assert isinstance(direct["id"], str)
        assert isinstance(parsed["id"], str)
        assert isinstance(direct["val"], int)
        assert isinstance(parsed["val"], int)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
