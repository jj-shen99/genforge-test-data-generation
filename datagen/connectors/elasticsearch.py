"""Elasticsearch / OpenSearch connector — push documents via Bulk API."""

from __future__ import annotations

import json
import time
from typing import Any

from datagen.connectors.base import (
    AuthMethod, BaseConnector, ConnectionConfig,
    ConnectorStatus, HealthCheck, PushResult,
)
from datagen.connectors.auth import AuthProvider
from datagen.connectors.registry import register_connector


@register_connector
class ElasticsearchConnector(BaseConnector):
    CONNECTOR_TYPE = "elasticsearch"
    DISPLAY_NAME = "Elasticsearch / OpenSearch"
    SUPPORTED_AUTH = [AuthMethod.BASIC, AuthMethod.API_KEY, AuthMethod.BEARER_TOKEN]
    CATEGORY = "observability"

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._client = None
        self._index = config.options.get("index", "test-data")
        self._pipeline = config.options.get("pipeline")
        scheme = "https" if config.options.get("ssl", True) else "http"
        port = config.port or 9200
        self._base_url = f"{scheme}://{config.host}:{port}"

    def authenticate(self) -> bool:
        try:
            import httpx
            session = AuthProvider.create_session(self.config.auth)
            self._client = httpx.Client(
                base_url=self._base_url,
                headers={**session.headers, "Content-Type": "application/json"},
                verify=self.config.options.get("verify_ssl", True),
                timeout=30,
            )
            self.status = ConnectorStatus.CONNECTED
            return True
        except ImportError:
            raise ImportError("httpx not installed. Run: pip install httpx")
        except Exception as e:
            self.status = ConnectorStatus.ERROR
            raise ConnectionError(f"Elasticsearch connection failed: {e}")

    def validate_connection(self) -> HealthCheck:
        start = time.time()
        try:
            if self._client is None:
                self.authenticate()
            resp = self._client.get("/_cluster/health")
            latency = (time.time() - start) * 1000
            if resp.status_code == 200:
                data = resp.json()
                return HealthCheck(
                    healthy=data.get("status") != "red",
                    latency_ms=round(latency, 1),
                    message=f"Cluster: {data.get('cluster_name')} status: {data.get('status')}",
                    details=data,
                )
            return HealthCheck(healthy=False, message=f"HTTP {resp.status_code}")
        except Exception as e:
            return HealthCheck(healthy=False, message=str(e))

    def push_batch(self, records: list[dict], **kwargs) -> PushResult:
        index = kwargs.get("index", self._index)
        start = time.time()

        try:
            if self._client is None:
                self.authenticate()

            # Build NDJSON bulk payload
            lines = []
            for record in records:
                action = {"index": {"_index": index}}
                if self._pipeline:
                    action["index"]["pipeline"] = self._pipeline
                lines.append(json.dumps(action))
                lines.append(json.dumps(record, default=str))
            body = "\n".join(lines) + "\n"

            resp = self._client.post(
                "/_bulk",
                content=body.encode(),
                headers={"Content-Type": "application/x-ndjson"},
            )

            if resp.status_code not in (200, 201):
                return PushResult(
                    success=False, errors=[f"HTTP {resp.status_code}: {resp.text[:300]}"],
                    duration_seconds=round(time.time() - start, 3),
                )

            result = resp.json()
            err_count = 0
            errs = []
            if result.get("errors"):
                for item in result.get("items", []):
                    action_result = item.get("index", item.get("create", {}))
                    if action_result.get("status", 200) >= 400:
                        err_count += 1
                        if len(errs) < 5:
                            errs.append(str(action_result.get("error", {}).get("reason", ""))[:200])

            return PushResult(
                success=err_count == 0,
                records_sent=len(records) - err_count,
                records_failed=err_count,
                errors=errs,
                duration_seconds=round(time.time() - start, 3),
                metadata={"index": index, "took_ms": result.get("took")},
            )

        except Exception as e:
            return PushResult(
                success=False, errors=[str(e)],
                duration_seconds=round(time.time() - start, 3),
            )

    def get_target_schema(self) -> dict | None:
        try:
            if self._client is None:
                self.authenticate()
            resp = self._client.get(f"/{self._index}/_mapping")
            if resp.status_code != 200:
                return None
            mappings = resp.json()
            index_data = next(iter(mappings.values()), {})
            props = index_data.get("mappings", {}).get("properties", {})
            es_to_json = {
                "text": "string", "keyword": "string", "long": "integer",
                "integer": "integer", "float": "number", "double": "number",
                "boolean": "boolean", "date": "string", "object": "object",
                "nested": "array", "ip": "string", "geo_point": "object",
            }
            json_props = {}
            for name, mapping in props.items():
                es_type = mapping.get("type", "object")
                json_type = es_to_json.get(es_type, "string")
                prop: dict[str, Any] = {"type": json_type}
                if es_type == "date":
                    prop["format"] = "date-time"
                elif es_type == "ip":
                    prop["format"] = "ipv4"
                json_props[name] = prop
            return {"type": "object", "properties": json_props} if json_props else None
        except Exception:
            return None

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
        super().close()
