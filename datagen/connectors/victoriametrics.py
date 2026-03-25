"""VictoriaMetrics connector — push metrics via import API."""

from __future__ import annotations

import time
from typing import Any

from datagen.connectors.base import (
    AuthMethod, BaseConnector, ConnectionConfig,
    ConnectorStatus, HealthCheck, PushResult,
)
from datagen.connectors.auth import AuthProvider
from datagen.connectors.registry import register_connector


@register_connector
class VictoriaMetricsConnector(BaseConnector):
    CONNECTOR_TYPE = "victoriametrics"
    DISPLAY_NAME = "VictoriaMetrics"
    SUPPORTED_AUTH = [AuthMethod.BASIC, AuthMethod.BEARER_TOKEN]
    CATEGORY = "observability"

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._client = None
        scheme = "https" if config.options.get("ssl", False) else "http"
        port = config.port or 8428
        # Use the host as-is if it already contains a scheme
        if config.host.startswith("http://") or config.host.startswith("https://"):
            base = config.host.rstrip("/")
        else:
            base = f"{scheme}://{config.host}:{port}"
        # Support both import and write endpoints
        api_mode = config.options.get("api_mode", "import")
        if api_mode == "write":
            self._push_url = f"{base}/api/v1/write"
        else:
            self._push_url = f"{base}/api/v1/import"
        self._health_url = f"{base}/api/v1/status/tsdb"

    def authenticate(self) -> bool:
        try:
            import httpx
            session = AuthProvider.create_session(self.config.auth)
            self._client = httpx.Client(
                headers=session.headers,
                verify=self.config.options.get("verify_ssl", False),
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
                                 message="VictoriaMetrics reachable")
            return HealthCheck(healthy=False, message=f"HTTP {resp.status_code}")
        except Exception as e:
            return HealthCheck(healthy=False, message=str(e))

    def push_batch(self, records: list[dict], **kwargs) -> PushResult:
        """Push metrics to VictoriaMetrics.

        Supports two modes:
        - import: JSON line format via /api/v1/import (default)
        - write: Prometheus remote write format via /api/v1/write

        Each record should have: metric, value, timestamp (ISO or epoch),
        and optionally labels (dict).
        """
        start = time.time()
        try:
            if self._client is None:
                self.authenticate()

            if "/import" in self._push_url:
                return self._push_import(records, start)
            else:
                return self._push_write(records, start)

        except Exception as e:
            return PushResult(
                success=False, errors=[str(e)],
                duration_seconds=round(time.time() - start, 3),
            )

    def _push_import(self, records: list[dict], start: float) -> PushResult:
        """Push via /api/v1/import using JSON line format.

        VictoriaMetrics expects newline-delimited JSON where each line is:
        {"metric":{"__name__":"metric_name","label":"value"},"values":[1.0],"timestamps":[1609459200000]}
        """
        lines = []
        for record in records:
            metric_name = record.get("metric", "test_metric")
            labels = record.get("labels", {})
            value = record.get("value", 0)
            # Parse timestamp
            ts = record.get("timestamp", record.get("timestamp_epoch_ms"))
            if isinstance(ts, str):
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    ts_ms = int(dt.timestamp() * 1000)
                except Exception:
                    ts_ms = int(time.time() * 1000)
            elif isinstance(ts, (int, float)):
                ts_ms = int(ts) if ts > 1e12 else int(ts * 1000)
            else:
                ts_ms = int(time.time() * 1000)

            metric_labels = {"__name__": metric_name}
            metric_labels.update({k: str(v) for k, v in labels.items()})
            # Add any extra string fields as labels
            for k, v in record.items():
                if k not in ("metric", "value", "timestamp", "timestamp_epoch_ms", "labels") and isinstance(v, str):
                    metric_labels[k] = v

            line = {
                "metric": metric_labels,
                "values": [float(value)],
                "timestamps": [ts_ms],
            }
            lines.append(line)

        # Send as newline-delimited JSON
        import json
        body = "\n".join(json.dumps(line) for line in lines)
        resp = self._client.post(
            self._push_url,
            content=body,
            headers={"Content-Type": "application/json"},
        )

        if resp.status_code in (200, 204):
            return PushResult(
                success=True,
                records_sent=len(records),
                duration_seconds=round(time.time() - start, 3),
                metadata={"endpoint": self._push_url, "lines": len(lines)},
            )
        else:
            return PushResult(
                success=False,
                records_failed=len(records),
                errors=[f"HTTP {resp.status_code}: {resp.text[:300]}"],
                duration_seconds=round(time.time() - start, 3),
            )

    def _push_write(self, records: list[dict], start: float) -> PushResult:
        """Push via /api/v1/write using Prometheus remote write text format.

        VictoriaMetrics /api/v1/write accepts Prometheus text exposition format:
        metric_name{label="value"} value timestamp_ms
        """
        lines = []
        for record in records:
            metric_name = record.get("metric", "test_metric")
            labels = record.get("labels", {})
            value = record.get("value", 0)
            ts = record.get("timestamp", record.get("timestamp_epoch_ms"))
            if isinstance(ts, str):
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    ts_ms = int(dt.timestamp() * 1000)
                except Exception:
                    ts_ms = int(time.time() * 1000)
            elif isinstance(ts, (int, float)):
                ts_ms = int(ts) if ts > 1e12 else int(ts * 1000)
            else:
                ts_ms = int(time.time() * 1000)

            # Add extra string fields as labels
            extra_labels = {}
            for k, v in record.items():
                if k not in ("metric", "value", "timestamp", "timestamp_epoch_ms", "labels") and isinstance(v, str):
                    extra_labels[k] = v
            all_labels = {**labels, **extra_labels}

            if all_labels:
                label_str = ",".join(f'{k}="{v}"' for k, v in all_labels.items())
                lines.append(f"{metric_name}{{{label_str}}} {value} {ts_ms}")
            else:
                lines.append(f"{metric_name} {value} {ts_ms}")

        body = "\n".join(lines)
        resp = self._client.post(
            self._push_url,
            content=body,
            headers={"Content-Type": "text/plain"},
        )

        if resp.status_code in (200, 204):
            return PushResult(
                success=True,
                records_sent=len(records),
                duration_seconds=round(time.time() - start, 3),
                metadata={"endpoint": self._push_url, "lines": len(lines)},
            )
        else:
            return PushResult(
                success=False,
                records_failed=len(records),
                errors=[f"HTTP {resp.status_code}: {resp.text[:300]}"],
                duration_seconds=round(time.time() - start, 3),
            )

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
        super().close()
