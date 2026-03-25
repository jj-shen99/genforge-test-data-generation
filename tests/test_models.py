"""Tests for Pydantic API models."""

import pytest
from pydantic import ValidationError

from datagen.models.models import (
    AuthMethodEnum,
    ConnectionCreateRequest,
    ConnectionResponse,
    ConnectionTestResult,
    DashboardStats,
    GenerateRequest,
    GenerateResponse,
    JobCreateRequest,
    JobResponse,
    JobStatus,
    PipelineJobRequest,
    SchemaCreateRequest,
    SchemaResponse,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TestEnums:
    def test_job_status_values(self):
        assert JobStatus.PENDING == "pending"
        assert JobStatus.RUNNING == "running"
        assert JobStatus.COMPLETED == "completed"
        assert JobStatus.FAILED == "failed"
        assert JobStatus.CANCELLED == "cancelled"

    def test_auth_method_values(self):
        assert AuthMethodEnum.BASIC == "basic"
        assert AuthMethodEnum.API_KEY == "api_key"
        assert AuthMethodEnum.BEARER_TOKEN == "bearer_token"
        assert AuthMethodEnum.AWS_IAM == "aws_iam"


# ---------------------------------------------------------------------------
# Schema models
# ---------------------------------------------------------------------------

class TestSchemaModels:
    def test_create_request_minimal(self):
        req = SchemaCreateRequest(
            name="Test Schema",
            schema={"type": "object", "properties": {"id": {"type": "string"}}},
        )
        assert req.name == "Test Schema"
        assert req.schema_def["type"] == "object"
        assert req.category == "custom"
        assert req.tags == []

    def test_create_request_full(self):
        req = SchemaCreateRequest(
            name="Incident",
            description="ServiceNow incidents",
            schema={"type": "object", "properties": {}},
            category="servicenow",
            tags=["itsm", "incident"],
        )
        assert req.description == "ServiceNow incidents"
        assert req.category == "servicenow"
        assert len(req.tags) == 2

    def test_create_request_missing_schema(self):
        with pytest.raises(ValidationError):
            SchemaCreateRequest(name="Bad")

    def test_create_request_missing_name(self):
        with pytest.raises(ValidationError):
            SchemaCreateRequest(schema={"type": "object"})

    def test_schema_response(self):
        resp = SchemaResponse(
            id="s1", name="Test", description="desc",
            schema={"type": "object"}, category="custom",
            tags=[], created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        assert resp.id == "s1"
        assert resp.schema_def == {"type": "object"}


# ---------------------------------------------------------------------------
# Connection models
# ---------------------------------------------------------------------------

class TestConnectionModels:
    def test_create_request_defaults(self):
        req = ConnectionCreateRequest(
            name="My ES", connector_type="elasticsearch", host="localhost",
        )
        assert req.port is None
        assert req.auth_method == AuthMethodEnum.BASIC
        assert req.credentials == {}
        assert req.options == {}

    def test_create_request_full(self):
        req = ConnectionCreateRequest(
            name="Prod Kafka", connector_type="kafka",
            host="kafka.prod.internal", port=9092,
            auth_method=AuthMethodEnum.API_KEY,
            credentials={"key": "abc"},
            options={"topic": "events"},
        )
        assert req.port == 9092
        assert req.options["topic"] == "events"

    def test_create_request_missing_required(self):
        with pytest.raises(ValidationError):
            ConnectionCreateRequest(name="bad")

    def test_connection_response(self):
        resp = ConnectionResponse(
            id="c1", name="Test", connector_type="elasticsearch",
            host="localhost", port=9200, auth_method="basic",
            options={}, created_at="2026-01-01",
        )
        assert resp.status == "unknown"
        assert resp.last_health_check is None

    def test_connection_test_result(self):
        r = ConnectionTestResult(healthy=True, latency_ms=5.2, message="OK")
        assert r.healthy
        assert r.latency_ms == 5.2


# ---------------------------------------------------------------------------
# Job models
# ---------------------------------------------------------------------------

class TestJobModels:
    def test_job_create_defaults(self):
        req = JobCreateRequest(schema_id="s1", connection_id="c1")
        assert req.count == 100
        assert req.batch_size == 500
        assert req.options == {}

    def test_job_create_custom(self):
        req = JobCreateRequest(
            schema_id="s1", connection_id="c1",
            count=5000, batch_size=100, options={"table": "test"},
        )
        assert req.count == 5000
        assert req.batch_size == 100

    def test_job_response(self):
        resp = JobResponse(
            id="j1", schema_id="s1", connection_id="c1",
            status=JobStatus.COMPLETED, count=100,
            records_sent=100, records_failed=0,
        )
        assert resp.status == JobStatus.COMPLETED
        assert resp.progress_pct == 0

    def test_pipeline_job(self):
        steps = [
            JobCreateRequest(schema_id="s1", connection_id="c1", count=10),
            JobCreateRequest(schema_id="s2", connection_id="c1", count=20),
        ]
        pipeline = PipelineJobRequest(name="ITSM pipeline", steps=steps)
        assert len(pipeline.steps) == 2
        assert pipeline.steps[0].count == 10


# ---------------------------------------------------------------------------
# Generate models
# ---------------------------------------------------------------------------

class TestGenerateModels:
    def test_generate_request_defaults(self):
        req = GenerateRequest(schema={"type": "object", "properties": {}})
        assert req.count == 10
        assert req.output_format == "json"

    def test_generate_request_custom(self):
        req = GenerateRequest(
            schema={"type": "object"}, count=500, output_format="csv",
        )
        assert req.count == 500
        assert req.output_format == "csv"

    def test_generate_response(self):
        resp = GenerateResponse(
            records=[{"a": 1}, {"a": 2}], count=2, duration_ms=15.3,
        )
        assert len(resp.records) == 2
        assert resp.duration_ms == 15.3

    def test_generate_request_missing_schema(self):
        with pytest.raises(ValidationError):
            GenerateRequest(count=10)


# ---------------------------------------------------------------------------
# Dashboard models
# ---------------------------------------------------------------------------

class TestDashboardModels:
    def test_dashboard_stats(self):
        stats = DashboardStats(
            total_schemas=54, total_connections=3, total_jobs=10,
            records_generated=5000, active_jobs=1,
            connectors_available=[{"type": "elasticsearch", "name": "ES"}],
        )
        assert stats.total_schemas == 54
        assert len(stats.connectors_available) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
