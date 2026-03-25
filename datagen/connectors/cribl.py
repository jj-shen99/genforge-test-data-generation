"""Cribl connector — send events via Cribl Stream HTTP/HEC endpoint."""

from __future__ import annotations

import json
import time

from datagen.connectors.base import (
    AuthMethod, BaseConnector, ConnectionConfig,
    ConnectorStatus, HealthCheck, PushResult,
)
from datagen.connectors.auth import AuthProvider
from datagen.connectors.registry import register_connector


@register_connector
class CriblConnector(BaseConnector):
    CONNECTOR_TYPE = "cribl"
    DISPLAY_NAME = "Cribl Stream"
    SUPPORTED_AUTH = [AuthMethod.BEARER_TOKEN, AuthMethod.API_KEY]
    CATEGORY = "observability"

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._client = None
        scheme = "https" if config.options.get("ssl", True) else "http"
        port = config.port or 9514
        if config.host.startswith("http://") or config.host.startswith("https://"):
            base = config.host.rstrip("/")
        else:
            base = f"{scheme}://{config.host}:{port}"
        self._events_url = f"{base}/api/v1/events"
        self._health_url = f"{base}/api/v1/health"

    def authenticate(self) -> bool:
        try:
            import httpx
            session = AuthProvider.create_session(self.config.auth)
            self._client = httpx.Client(
                headers=session.headers,
                verify=self.config.options.get("verify_ssl", True),
                timeout=30,
            )
            self.status = ConnectorStatus.CONNECTED
            return True
        except ImportError:
            raise ImportError("httpx not installed. Run: pip install httpx")

    def validate_connection(self) -> HealthCheck:
        start = time.time()
        try:
            if self._client is None:
                self.authenticate()
            resp = self._client.get(self._health_url)
            latency = (time.time() - start) * 1000
            if resp.status_code == 200:
                return HealthCheck(healthy=True, latency_ms=round(latency, 1),
                                 message="Cribl Stream reachable")
            return HealthCheck(healthy=False, message=f"HTTP {resp.status_code}")
        except Exception as e:
            return HealthCheck(healthy=False, message=str(e))

    def push_batch(self, records: list[dict], **kwargs) -> PushResult:
        start = time.time()
        try:
            if self._client is None:
                self.authenticate()

            # Cribl HEC accepts JSON array or NDJSON
            payload = json.dumps(records, default=str)
            resp = self._client.post(
                self._events_url,
                content=payload,
                headers={"Content-Type": "application/json"},
            )

            if resp.status_code in (200, 201, 204):
                return PushResult(
                    success=True, records_sent=len(records),
                    duration_seconds=round(time.time() - start, 3),
                    metadata={"endpoint": self._events_url},
                )
            else:
                return PushResult(
                    success=False, records_failed=len(records),
                    errors=[f"HTTP {resp.status_code}: {resp.text[:300]}"],
                    duration_seconds=round(time.time() - start, 3),
                )
        except Exception as e:
            return PushResult(success=False, errors=[str(e)],
                            duration_seconds=round(time.time() - start, 3))

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
        super().close()
