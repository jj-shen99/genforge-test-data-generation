"""Prometheus connector — push metrics via Remote Write API."""

from __future__ import annotations

import struct
import time
from typing import Any

from datagen.connectors.base import (
    AuthMethod, BaseConnector, ConnectionConfig,
    ConnectorStatus, HealthCheck, PushResult,
)
from datagen.connectors.auth import AuthProvider
from datagen.connectors.registry import register_connector


@register_connector
class PrometheusConnector(BaseConnector):
    CONNECTOR_TYPE = "prometheus"
    DISPLAY_NAME = "Prometheus Remote Write"
    SUPPORTED_AUTH = [AuthMethod.BASIC, AuthMethod.BEARER_TOKEN, AuthMethod.MTLS]
    CATEGORY = "observability"

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._client = None
        scheme = "https" if config.options.get("ssl", True) else "http"
        port = config.port or 9090
        path = config.options.get("write_path", "/api/v1/write")
        self._write_url = f"{scheme}://{config.host}:{port}{path}"
        self._read_url = f"{scheme}://{config.host}:{port}/api/v1/query"

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
            resp = self._client.get(self._read_url, params={"query": "up"})
            latency = (time.time() - start) * 1000
            if resp.status_code == 200:
                return HealthCheck(healthy=True, latency_ms=round(latency, 1),
                                 message="Prometheus reachable")
            return HealthCheck(healthy=False, message=f"HTTP {resp.status_code}")
        except Exception as e:
            return HealthCheck(healthy=False, message=str(e))

    def push_batch(self, records: list[dict], **kwargs) -> PushResult:
        """Push time-series data points.

        Each record should have: metric, value, timestamp_epoch_ms, labels
        Uses the Prometheus remote write JSON format.
        """
        start = time.time()
        try:
            if self._client is None:
                self.authenticate()

            # Group by metric name for efficient write
            timeseries: dict[str, dict] = {}
            for record in records:
                metric = record.get("metric", "test_metric")
                labels = record.get("labels", {})
                label_key = f"{metric}|{'|'.join(f'{k}={v}' for k, v in sorted(labels.items()))}"

                if label_key not in timeseries:
                    label_list = [{"name": "__name__", "value": metric}]
                    label_list.extend(
                        {"name": k, "value": str(v)} for k, v in labels.items()
                    )
                    timeseries[label_key] = {"labels": label_list, "samples": []}

                timeseries[label_key]["samples"].append({
                    "value": record.get("value", 0),
                    "timestamp": record.get("timestamp_epoch_ms", int(time.time() * 1000)),
                })

            payload = {"timeseries": list(timeseries.values())}

            resp = self._client.post(
                self._write_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            if resp.status_code in (200, 204):
                return PushResult(
                    success=True,
                    records_sent=len(records),
                    duration_seconds=round(time.time() - start, 3),
                    metadata={"timeseries_count": len(timeseries)},
                )
            else:
                return PushResult(
                    success=False,
                    records_failed=len(records),
                    errors=[f"HTTP {resp.status_code}: {resp.text[:300]}"],
                    duration_seconds=round(time.time() - start, 3),
                )

        except Exception as e:
            return PushResult(
                success=False, errors=[str(e)],
                duration_seconds=round(time.time() - start, 3),
            )

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
        super().close()
