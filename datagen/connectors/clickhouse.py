"""ClickHouse connector — insert data via HTTP interface."""

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
class ClickHouseConnector(BaseConnector):
    CONNECTOR_TYPE = "clickhouse"
    DISPLAY_NAME = "ClickHouse"
    SUPPORTED_AUTH = [AuthMethod.BASIC]
    CATEGORY = "database"

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._client = None
        scheme = "https" if config.options.get("ssl", False) else "http"
        port = config.port or 8123
        if config.host.startswith("http://") or config.host.startswith("https://"):
            base = config.host.rstrip("/")
        else:
            base = f"{scheme}://{config.host}:{port}"
        self._base_url = base
        self._database = config.options.get("database", "default")
        self._table = config.options.get("table", "events")

    def authenticate(self) -> bool:
        try:
            import httpx
            session = AuthProvider.create_session(self.config.auth)
            self._client = httpx.Client(
                headers=session.headers,
                verify=self.config.options.get("verify_ssl", False),
                timeout=60,
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
            resp = self._client.get(f"{self._base_url}/ping")
            latency = (time.time() - start) * 1000
            if resp.status_code == 200:
                return HealthCheck(healthy=True, latency_ms=round(latency, 1),
                                 message="ClickHouse reachable")
            return HealthCheck(healthy=False, message=f"HTTP {resp.status_code}")
        except Exception as e:
            return HealthCheck(healthy=False, message=str(e))

    def push_batch(self, records: list[dict], **kwargs) -> PushResult:
        """Insert records into ClickHouse using JSONEachRow format via HTTP interface."""
        start = time.time()
        table = kwargs.get("table", self._table)
        database = kwargs.get("database", self._database)

        try:
            if self._client is None:
                self.authenticate()

            # Build JSONEachRow payload (newline-delimited JSON)
            body = "\n".join(json.dumps(r, default=str) for r in records)

            query = f"INSERT INTO {database}.{table} FORMAT JSONEachRow"
            resp = self._client.post(
                self._base_url,
                params={"query": query},
                content=body,
                headers={"Content-Type": "application/json"},
            )

            if resp.status_code == 200:
                return PushResult(
                    success=True, records_sent=len(records),
                    duration_seconds=round(time.time() - start, 3),
                    metadata={"database": database, "table": table},
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
