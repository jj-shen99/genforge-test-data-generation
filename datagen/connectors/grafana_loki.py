"""Grafana Loki connector — push log entries via Loki push API."""

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
class GrafanaLokiConnector(BaseConnector):
    CONNECTOR_TYPE = "grafana_loki"
    DISPLAY_NAME = "Grafana Loki"
    SUPPORTED_AUTH = [AuthMethod.BASIC, AuthMethod.BEARER_TOKEN, AuthMethod.API_KEY]
    CATEGORY = "observability"

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._client = None
        scheme = "https" if config.options.get("ssl", False) else "http"
        port = config.port or 3100
        if config.host.startswith("http://") or config.host.startswith("https://"):
            base = config.host.rstrip("/")
        else:
            base = f"{scheme}://{config.host}:{port}"
        self._push_url = f"{base}/loki/api/v1/push"
        self._ready_url = f"{base}/ready"

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
            resp = self._client.get(self._ready_url)
            latency = (time.time() - start) * 1000
            if resp.status_code == 200:
                return HealthCheck(healthy=True, latency_ms=round(latency, 1),
                                 message="Grafana Loki reachable")
            return HealthCheck(healthy=False, message=f"HTTP {resp.status_code}")
        except Exception as e:
            return HealthCheck(healthy=False, message=str(e))

    def push_batch(self, records: list[dict], **kwargs) -> PushResult:
        """Push log entries to Loki.

        Each record should have: timestamp (ISO), message/line, and optionally
        level, container, namespace, etc. as label fields.
        """
        start = time.time()
        try:
            if self._client is None:
                self.authenticate()

            # Group records by label set for efficient push
            label_fields = self.config.options.get("label_fields",
                ["level", "container", "namespace", "stream", "service"])
            streams: dict[str, dict] = {}

            for record in records:
                labels = {}
                for f in label_fields:
                    if f in record and isinstance(record[f], str):
                        labels[f] = record[f]
                if not labels:
                    labels["source"] = "genforge"

                label_key = json.dumps(labels, sort_keys=True)
                if label_key not in streams:
                    label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
                    streams[label_key] = {
                        "stream": labels,
                        "values": [],
                    }

                ts = record.get("timestamp", "")
                if isinstance(ts, str) and ts:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        ts_ns = str(int(dt.timestamp() * 1e9))
                    except Exception:
                        ts_ns = str(int(time.time() * 1e9))
                else:
                    ts_ns = str(int(time.time() * 1e9))

                line = record.get("message", record.get("line", json.dumps(record, default=str)))
                streams[label_key]["values"].append([ts_ns, str(line)])

            payload = {"streams": list(streams.values())}

            resp = self._client.post(
                self._push_url,
                content=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )

            if resp.status_code in (200, 204):
                return PushResult(
                    success=True, records_sent=len(records),
                    duration_seconds=round(time.time() - start, 3),
                    metadata={"streams": len(streams)},
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
