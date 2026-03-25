"""Tests for the GenForge schema engine, generators, and pipeline."""

import json
import re
import uuid
from pathlib import Path

import pytest

from datagen.engine.generators import (
    gen_string, gen_integer, gen_number, gen_boolean,
    gen_datetime, gen_array, sample_distribution, weighted_choice,
)
from datagen.engine.schema_parser import SchemaParser, generate_value, generate_record
from datagen.engine.timeseries import TimeSeriesGenerator, generate_log_entries
from datagen.engine.pipeline import GenerationPipeline, servicenow_itsm_pipeline


# ---------------------------------------------------------------------------
# Generator tests
# ---------------------------------------------------------------------------

class TestStringGenerator:
    def test_basic_string(self):
        result = gen_string({"type": "string"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_enum(self):
        schema = {"type": "string", "enum": ["a", "b", "c"]}
        for _ in range(20):
            result = gen_string(schema)
            assert result in ["a", "b", "c"]

    def test_weighted_enum(self):
        schema = {"type": "string", "enum": ["rare", "common"],
                  "x-datagen-weight": [1, 99]}
        results = [gen_string(schema) for _ in range(200)]
        common_count = results.count("common")
        assert common_count > 150  # Should be heavily weighted toward "common"

    def test_pattern(self):
        schema = {"type": "string", "pattern": "INC[0-9]{7}"}
        result = gen_string(schema)
        assert result.startswith("INC")
        assert len(result) == 10
        assert result[3:].isdigit()

    def test_faker(self):
        schema = {"type": "string", "x-datagen-faker": "person.name"}
        result = gen_string(schema)
        assert isinstance(result, str)
        assert len(result) > 2

    def test_format_email(self):
        result = gen_string({"type": "string", "format": "email"})
        assert "@" in result

    def test_format_uuid(self):
        result = gen_string({"type": "string", "format": "uuid"})
        uuid.UUID(result)  # Should not raise

    def test_format_ipv4(self):
        result = gen_string({"type": "string", "format": "ipv4"})
        parts = result.split(".")
        assert len(parts) == 4


class TestIntegerGenerator:
    def test_basic(self):
        result = gen_integer({"type": "integer"})
        assert isinstance(result, int)

    def test_range(self):
        schema = {"type": "integer", "minimum": 10, "maximum": 20}
        for _ in range(50):
            result = gen_integer(schema)
            assert 10 <= result <= 20

    def test_enum(self):
        schema = {"type": "integer", "enum": [1, 2, 3, 4]}
        for _ in range(20):
            assert gen_integer(schema) in [1, 2, 3, 4]

    def test_distribution(self):
        schema = {"type": "integer", "x-datagen-distribution": {
            "type": "gaussian", "mean": 50, "stddev": 10
        }}
        results = [gen_integer(schema) for _ in range(100)]
        avg = sum(results) / len(results)
        assert 30 < avg < 70


class TestNumberGenerator:
    def test_basic(self):
        result = gen_number({"type": "number"})
        assert isinstance(result, float)

    def test_precision(self):
        schema = {"type": "number", "x-datagen-precision": 2,
                  "minimum": 0, "maximum": 100}
        result = gen_number(schema)
        assert len(str(result).split(".")[-1]) <= 2


class TestBooleanGenerator:
    def test_basic(self):
        result = gen_boolean({"type": "boolean"})
        assert isinstance(result, bool)

    def test_weighted(self):
        schema = {"type": "boolean", "x-datagen-weight": 0.95}
        results = [gen_boolean(schema) for _ in range(200)]
        true_count = sum(results)
        assert true_count > 150


class TestDistributions:
    def test_uniform(self):
        val = sample_distribution({"type": "uniform", "min": 0, "max": 10})
        assert 0 <= val <= 10

    def test_gaussian(self):
        vals = [sample_distribution({"type": "gaussian", "mean": 50, "stddev": 5})
                for _ in range(100)]
        avg = sum(vals) / len(vals)
        assert 40 < avg < 60

    def test_poisson(self):
        val = sample_distribution({"type": "poisson", "lambda": 5})
        assert isinstance(val, (int, float))
        assert val >= 0


# ---------------------------------------------------------------------------
# Schema parser tests
# ---------------------------------------------------------------------------

class TestSchemaParser:
    def test_simple_object(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "x-datagen-faker": "person.name"},
                "age": {"type": "integer", "minimum": 18, "maximum": 90},
                "active": {"type": "boolean"},
            }
        }
        parser = SchemaParser(schema)
        records = parser.generate(count=5)
        assert len(records) == 5
        for r in records:
            assert "name" in r
            assert "age" in r
            assert isinstance(r["active"], bool)
            assert 18 <= r["age"] <= 90

    def test_nested_object(self):
        schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "x-datagen-faker": "person.name"},
                        "email": {"type": "string", "format": "email"},
                    }
                },
                "score": {"type": "number", "minimum": 0, "maximum": 100},
            }
        }
        parser = SchemaParser(schema)
        records = parser.generate(count=3)
        for r in records:
            assert isinstance(r["user"], dict)
            assert "name" in r["user"]
            assert "@" in r["user"]["email"]

    def test_uniqueness(self):
        schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string", "format": "uuid", "x-datagen-unique": True}
            }
        }
        parser = SchemaParser(schema)
        records = parser.generate(count=50)
        ids = [r["id"] for r in records]
        assert len(set(ids)) == 50

    def test_null_rate(self):
        schema = {
            "type": "object",
            "properties": {
                "optional_field": {
                    "type": "string",
                    "x-datagen-faker": "lorem.word",
                    "x-datagen-null-rate": 0.5,
                }
            }
        }
        parser = SchemaParser(schema)
        records = parser.generate(count=200)
        null_count = sum(1 for r in records if r["optional_field"] is None)
        # Should be roughly 50% null (allow wide margin)
        assert 50 < null_count < 150

    def test_dependency(self):
        schema = {
            "type": "object",
            "properties": {
                "priority": {"type": "integer", "enum": [1, 4]},
                "state": {
                    "type": "integer",
                    "enum": [1, 2, 3, 6, 7],
                    "x-datagen-depends-on": {
                        "field": "priority",
                        "rules": {
                            "1": {"enum": [1, 2], "x-datagen-weight": [50, 50]},
                            "4": {"enum": [6, 7], "x-datagen-weight": [50, 50]}
                        }
                    }
                }
            }
        }
        parser = SchemaParser(schema)
        records = parser.generate(count=100)
        for r in records:
            if r["priority"] == 1:
                assert r["state"] in [1, 2]
            elif r["priority"] == 4:
                assert r["state"] in [6, 7]

    def test_array(self):
        schema = {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "string", "x-datagen-faker": "lorem.word"},
                    "minItems": 1,
                    "maxItems": 5,
                }
            }
        }
        parser = SchemaParser(schema)
        records = parser.generate(count=5)
        for r in records:
            assert isinstance(r["tags"], list)
            assert 1 <= len(r["tags"]) <= 5

    def test_ref_resolution(self):
        schema = {
            "type": "object",
            "$defs": {
                "address": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "x-datagen-faker": "address.city"},
                        "zip": {"type": "string", "x-datagen-faker": "address.zipcode"},
                    }
                }
            },
            "properties": {
                "home": {"$ref": "#/$defs/address"},
                "work": {"$ref": "#/$defs/address"},
            }
        }
        parser = SchemaParser(schema)
        records = parser.generate(count=3)
        for r in records:
            assert "city" in r["home"]
            assert "city" in r["work"]

    def test_from_file(self):
        schema_path = Path(__file__).parent / "configs" / "schemas" / "servicenow_incident.json"
        if schema_path.exists():
            parser = SchemaParser(schema_path)
            records = parser.generate(count=10)
            assert len(records) == 10
            for r in records:
                assert r["number"].startswith("INC")
                assert r["priority"] in [1, 2, 3, 4]


# ---------------------------------------------------------------------------
# Time-series tests
# ---------------------------------------------------------------------------

class TestTimeSeries:
    def test_sine_pattern(self):
        gen = TimeSeriesGenerator({
            "pattern": "sine",
            "start": "now-1h",
            "end": "now",
            "interval_seconds": 60,
            "base_value": 50,
            "amplitude": 25,
        })
        points = gen.generate()
        assert len(points) > 50
        assert all("value" in p and "timestamp" in p for p in points)

    def test_random_walk(self):
        gen = TimeSeriesGenerator({
            "pattern": "random_walk",
            "start": "now-1h",
            "end": "now",
            "interval_seconds": 30,
        })
        points = gen.generate()
        assert len(points) > 100

    def test_seasonal(self):
        gen = TimeSeriesGenerator({
            "pattern": "seasonal",
            "start": "now-48h",
            "end": "now",
            "interval_seconds": 3600,
        })
        points = gen.generate()
        assert len(points) >= 48

    def test_log_entries(self):
        logs = generate_log_entries({"count": 50, "start": "now-1h"})
        assert len(logs) == 50
        levels = {l["level"] for l in logs}
        assert levels.issubset({"DEBUG", "INFO", "WARN", "ERROR"})


# ---------------------------------------------------------------------------
# Pipeline tests
# ---------------------------------------------------------------------------

class TestPipeline:
    def test_simple_pipeline(self):
        pipeline = GenerationPipeline()
        pipeline.add_schema(
            "users",
            {"type": "object", "properties": {
                "id": {"type": "string", "format": "uuid", "x-datagen-unique": True},
                "name": {"type": "string", "x-datagen-faker": "person.name"},
            }},
            count=10,
            ref_tracking={"id": "user.id"},
        )
        pipeline.add_schema(
            "orders",
            {"type": "object", "properties": {
                "id": {"type": "string", "format": "uuid"},
                "user_id": {"type": "string", "x-datagen-ref": "user.id"},
                "amount": {"type": "number", "minimum": 10, "maximum": 500},
            }},
            count=30,
            depends_on=["users"],
        )

        result = pipeline.execute()
        assert result.total_records == 40
        assert result.execution_order == ["users", "orders"]
        assert len(result.datasets["users"]) == 10
        assert len(result.datasets["orders"]) == 30

        # Verify referential integrity
        user_ids = {u["id"] for u in result.datasets["users"]}
        for order in result.datasets["orders"]:
            assert order["user_id"] in user_ids

    def test_dependency_order(self):
        pipeline = GenerationPipeline()
        pipeline.add_schema("c", {"type": "object", "properties": {}},
                           count=1, depends_on=["b"])
        pipeline.add_schema("a", {"type": "object", "properties": {}}, count=1)
        pipeline.add_schema("b", {"type": "object", "properties": {}},
                           count=1, depends_on=["a"])

        order = pipeline.resolve_order()
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")

    def test_servicenow_pipeline(self):
        pipeline = servicenow_itsm_pipeline(
            user_count=10, ci_count=20,
            incident_count=50, change_count=10,
        )
        result = pipeline.execute()
        assert result.total_records == 90
        assert "sys_user" in result.datasets
        assert "cmdb_ci" in result.datasets
        assert "incident" in result.datasets
        assert "change_request" in result.datasets
        assert len(result.errors) == 0

        # Check referential integrity
        user_ids = {u["sys_id"] for u in result.datasets["sys_user"]}
        ci_ids = {c["sys_id"] for c in result.datasets["cmdb_ci"]}
        for inc in result.datasets["incident"]:
            if inc.get("assigned_to"):
                assert inc["assigned_to"] in user_ids
            if inc.get("cmdb_ci"):
                assert inc["cmdb_ci"] in ci_ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
