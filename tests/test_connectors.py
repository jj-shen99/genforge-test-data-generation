"""Tests for connector base classes, registry, and auth provider."""

import base64
import time

import pytest

from datagen.connectors.base import (
    AuthConfig, AuthMethod, BaseConnector, ConnectionConfig,
    ConnectorStatus, HealthCheck, PushResult,
)
from datagen.connectors.auth import AuthProvider, AuthSession, refresh_oauth2_token
from datagen.connectors.registry import (
    _CONNECTORS, create_connector, get_connector_class, list_connectors,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class TestDataClasses:
    def test_connection_config_defaults(self):
        cfg = ConnectionConfig(name="test", connector_type="foo", host="localhost")
        assert cfg.port is None
        assert cfg.auth is None
        assert cfg.options == {}

    def test_connection_config_full(self):
        auth = AuthConfig(method=AuthMethod.BASIC, credentials={"username": "u", "password": "p"})
        cfg = ConnectionConfig(
            name="test", connector_type="elasticsearch", host="es.local",
            port=9200, auth=auth, options={"index": "logs"},
        )
        assert cfg.port == 9200
        assert cfg.auth.method == AuthMethod.BASIC
        assert cfg.options["index"] == "logs"

    def test_push_result_defaults(self):
        r = PushResult(success=True)
        assert r.records_sent == 0
        assert r.records_failed == 0
        assert r.errors == []
        assert r.duration_seconds == 0.0
        assert r.metadata == {}

    def test_push_result_failure(self):
        r = PushResult(success=False, records_failed=5, errors=["timeout"])
        assert not r.success
        assert r.records_failed == 5
        assert "timeout" in r.errors

    def test_health_check_healthy(self):
        hc = HealthCheck(healthy=True, latency_ms=12.5, message="OK")
        assert hc.healthy
        assert hc.latency_ms == 12.5

    def test_health_check_unhealthy(self):
        hc = HealthCheck(healthy=False, message="Connection refused")
        assert not hc.healthy
        assert "refused" in hc.message

    def test_connector_status_values(self):
        assert ConnectorStatus.DISCONNECTED.value == "disconnected"
        assert ConnectorStatus.CONNECTED.value == "connected"
        assert ConnectorStatus.ERROR.value == "error"
        assert ConnectorStatus.RATE_LIMITED.value == "rate_limited"

    def test_auth_method_values(self):
        assert AuthMethod.BASIC.value == "basic"
        assert AuthMethod.API_KEY.value == "api_key"
        assert AuthMethod.BEARER_TOKEN.value == "bearer_token"
        assert AuthMethod.AWS_IAM.value == "aws_iam"
        assert AuthMethod.OAUTH2.value == "oauth2"
        assert AuthMethod.MTLS.value == "mtls"


# ---------------------------------------------------------------------------
# BaseConnector (concrete subclass for testing)
# ---------------------------------------------------------------------------

class DummyConnector(BaseConnector):
    CONNECTOR_TYPE = "dummy"
    DISPLAY_NAME = "Dummy"
    SUPPORTED_AUTH = [AuthMethod.BASIC]
    CATEGORY = "test"

    def __init__(self, config, *, fail_auth=False, fail_push=False):
        super().__init__(config)
        self._fail_auth = fail_auth
        self._fail_push = fail_push

    def authenticate(self) -> bool:
        if self._fail_auth:
            self.status = ConnectorStatus.ERROR
            raise ConnectionError("Auth failed")
        self.status = ConnectorStatus.CONNECTED
        return True

    def validate_connection(self) -> HealthCheck:
        return HealthCheck(healthy=True, latency_ms=1.0, message="OK")

    def push_batch(self, records, **kwargs) -> PushResult:
        if self._fail_push:
            return PushResult(success=False, records_failed=len(records), errors=["push error"])
        return PushResult(success=True, records_sent=len(records))


class TestBaseConnector:
    def _config(self):
        return ConnectionConfig(name="test", connector_type="dummy", host="localhost")

    def test_init_status(self):
        c = DummyConnector(self._config())
        assert c.status == ConnectorStatus.DISCONNECTED

    def test_authenticate_success(self):
        c = DummyConnector(self._config())
        assert c.authenticate() is True
        assert c.status == ConnectorStatus.CONNECTED

    def test_authenticate_failure(self):
        c = DummyConnector(self._config(), fail_auth=True)
        with pytest.raises(ConnectionError):
            c.authenticate()
        assert c.status == ConnectorStatus.ERROR

    def test_push_batch_success(self):
        c = DummyConnector(self._config())
        result = c.push_batch([{"a": 1}, {"a": 2}])
        assert result.success
        assert result.records_sent == 2

    def test_push_batch_failure(self):
        c = DummyConnector(self._config(), fail_push=True)
        result = c.push_batch([{"a": 1}])
        assert not result.success
        assert result.records_failed == 1

    def test_push_stream_batches(self):
        c = DummyConnector(self._config())
        records = iter([{"i": i} for i in range(12)])
        result = c.push_stream(records, batch_size=5)
        assert result.success
        assert result.records_sent == 12

    def test_push_stream_with_failures(self):
        c = DummyConnector(self._config(), fail_push=True)
        records = iter([{"i": i} for i in range(3)])
        result = c.push_stream(records, batch_size=10)
        assert not result.success
        assert result.records_failed == 3

    def test_get_target_schema_default(self):
        c = DummyConnector(self._config())
        assert c.get_target_schema() is None

    def test_health_check_delegates(self):
        c = DummyConnector(self._config())
        hc = c.health_check()
        assert hc.healthy

    def test_close(self):
        c = DummyConnector(self._config())
        c.authenticate()
        assert c.status == ConnectorStatus.CONNECTED
        c.close()
        assert c.status == ConnectorStatus.DISCONNECTED

    def test_context_manager(self):
        c = DummyConnector(self._config())
        with c as conn:
            assert conn.status == ConnectorStatus.CONNECTED
        assert c.status == ConnectorStatus.DISCONNECTED

    def test_repr(self):
        c = DummyConnector(self._config())
        r = repr(c)
        assert "DummyConnector" in r
        assert "localhost" in r
        assert "disconnected" in r


# ---------------------------------------------------------------------------
# Auth provider
# ---------------------------------------------------------------------------

class TestAuthProvider:
    def test_basic_auth(self):
        auth = AuthConfig(method=AuthMethod.BASIC, credentials={"username": "admin", "password": "secret"})
        session = AuthProvider.create_session(auth)
        assert session.method == AuthMethod.BASIC
        expected = base64.b64encode(b"admin:secret").decode()
        assert session.headers["Authorization"] == f"Basic {expected}"

    def test_api_key_header(self):
        auth = AuthConfig(method=AuthMethod.API_KEY, credentials={"key": "abc123", "header": "X-Custom"})
        session = AuthProvider.create_session(auth)
        assert session.headers["X-Custom"] == "abc123"

    def test_api_key_with_prefix(self):
        auth = AuthConfig(method=AuthMethod.API_KEY, credentials={"key": "abc123", "prefix": "Token "})
        session = AuthProvider.create_session(auth)
        assert session.headers["X-API-Key"] == "Token abc123"

    def test_api_key_query_param(self):
        auth = AuthConfig(method=AuthMethod.API_KEY, credentials={
            "key": "abc123", "in": "query", "param_name": "apikey"
        })
        session = AuthProvider.create_session(auth)
        assert session.headers == {}
        assert session.params == {"apikey": "abc123"}

    def test_bearer_token(self):
        auth = AuthConfig(method=AuthMethod.BEARER_TOKEN, credentials={"token": "mytoken"})
        session = AuthProvider.create_session(auth)
        assert session.headers["Authorization"] == "Bearer mytoken"
        assert session.token == "mytoken"

    def test_oauth2(self):
        auth = AuthConfig(method=AuthMethod.OAUTH2, credentials={
            "client_id": "cid", "client_secret": "csec", "token_url": "https://auth.example.com/token"
        })
        session = AuthProvider.create_session(auth)
        assert session.method == AuthMethod.OAUTH2
        assert session.extra["client_id"] == "cid"
        assert session.extra["grant_type"] == "client_credentials"

    def test_aws_iam(self):
        auth = AuthConfig(method=AuthMethod.AWS_IAM, credentials={
            "access_key": "AKIA...", "secret_key": "secret", "region": "eu-west-1"
        })
        session = AuthProvider.create_session(auth)
        assert session.method == AuthMethod.AWS_IAM
        assert session.extra["region"] == "eu-west-1"

    def test_unknown_method(self):
        auth = AuthConfig(method=AuthMethod.KERBEROS, credentials={})
        session = AuthProvider.create_session(auth)
        assert session.method == AuthMethod.KERBEROS
        assert session.headers == {}


class TestAuthSession:
    def test_not_expired_when_no_expiry(self):
        session = AuthSession(method=AuthMethod.BASIC, headers={})
        assert not session.is_expired

    def test_not_expired_when_future(self):
        session = AuthSession(method=AuthMethod.BASIC, headers={}, expires_at=time.time() + 3600)
        assert not session.is_expired

    def test_expired_when_past(self):
        session = AuthSession(method=AuthMethod.BASIC, headers={}, expires_at=time.time() - 100)
        assert session.is_expired

    def test_expired_within_buffer(self):
        session = AuthSession(method=AuthMethod.BASIC, headers={}, expires_at=time.time() + 10)
        assert session.is_expired  # within 30s buffer

    def test_refresh_oauth2_noop(self):
        session = AuthSession(method=AuthMethod.OAUTH2, headers={}, extra={"token_url": "https://example.com"})
        refreshed = refresh_oauth2_token(session)
        assert refreshed is session  # placeholder, returns same


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_connectors_loaded(self):
        """All 16 built-in connectors should be registered."""
        assert len(_CONNECTORS) >= 16

    def test_known_types_registered(self):
        expected_types = [
            "aws_dynamodb", "aws_kinesis", "aws_s3", "aws_sqs",
            "clickhouse", "cribl", "elasticsearch", "grafana_loki",
            "kafka", "mongodb", "postgresql", "prometheus",
            "redis", "servicenow", "trino", "victoriametrics",
        ]
        for t in expected_types:
            assert t in _CONNECTORS, f"Connector '{t}' not registered"

    def test_get_connector_class_exists(self):
        cls = get_connector_class("elasticsearch")
        assert cls is not None
        assert cls.CONNECTOR_TYPE == "elasticsearch"

    def test_get_connector_class_missing(self):
        cls = get_connector_class("nonexistent_connector")
        assert cls is None

    def test_create_connector(self):
        config = ConnectionConfig(
            name="test-es", connector_type="elasticsearch",
            host="localhost", port=9200,
        )
        connector = create_connector(config)
        assert connector.config.host == "localhost"
        assert connector.status == ConnectorStatus.DISCONNECTED

    def test_create_connector_unknown_type(self):
        config = ConnectionConfig(name="bad", connector_type="not_real", host="x")
        with pytest.raises(ValueError, match="Unknown connector type"):
            create_connector(config)

    def test_list_connectors(self):
        connectors = list_connectors()
        assert len(connectors) >= 16
        types = {c["type"] for c in connectors}
        assert "elasticsearch" in types
        assert "kafka" in types
        assert "aws_s3" in types

    def test_list_connectors_fields(self):
        connectors = list_connectors()
        for c in connectors:
            assert "type" in c
            assert "name" in c
            assert "category" in c
            assert "auth_methods" in c
            assert isinstance(c["auth_methods"], list)

    def test_connector_categories(self):
        connectors = list_connectors()
        categories = {c["category"] for c in connectors}
        expected = {"cloud", "database", "bigdata", "servicenow", "observability"}
        assert expected.issubset(categories)


# ---------------------------------------------------------------------------
# Connector metadata validation
# ---------------------------------------------------------------------------

class TestConnectorMetadata:
    """Verify every registered connector has valid metadata."""

    def test_all_connectors_have_display_name(self):
        for name, cls in _CONNECTORS.items():
            assert cls.DISPLAY_NAME, f"{name} has no DISPLAY_NAME"
            assert cls.DISPLAY_NAME != "Base Connector", f"{name} uses default DISPLAY_NAME"

    def test_all_connectors_have_supported_auth(self):
        for name, cls in _CONNECTORS.items():
            assert len(cls.SUPPORTED_AUTH) > 0, f"{name} has no SUPPORTED_AUTH"

    def test_all_connectors_have_category(self):
        for name, cls in _CONNECTORS.items():
            assert cls.CATEGORY != "generic", f"{name} uses default CATEGORY"

    def test_all_connectors_inherit_base(self):
        for name, cls in _CONNECTORS.items():
            assert issubclass(cls, BaseConnector), f"{name} does not inherit BaseConnector"

    def test_all_connectors_type_matches_key(self):
        for name, cls in _CONNECTORS.items():
            assert cls.CONNECTOR_TYPE == name, f"{name} has mismatched CONNECTOR_TYPE: {cls.CONNECTOR_TYPE}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
