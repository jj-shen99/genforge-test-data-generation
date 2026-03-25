"""ServiceNow connector — push data via Table API, Import Set API, and Event API."""

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
class ServiceNowConnector(BaseConnector):
    CONNECTOR_TYPE = "servicenow"
    DISPLAY_NAME = "ServiceNow"
    SUPPORTED_AUTH = [AuthMethod.BASIC, AuthMethod.OAUTH2, AuthMethod.API_KEY]
    CATEGORY = "servicenow"

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._session = None
        self._http_client = None
        self._instance = config.host.rstrip("/")
        if not self._instance.startswith("http"):
            self._instance = f"https://{self._instance}"
        self._table = config.options.get("table", "incident")
        self._api_mode = config.options.get("api_mode", "table")  # table, import_set, event
        self._batch_size = config.options.get("batch_size", 50)

    def authenticate(self) -> bool:
        try:
            import httpx
            self._session = AuthProvider.create_session(self.config.auth)

            if self.config.auth.method == AuthMethod.OAUTH2:
                # Perform OAuth2 token exchange
                token_url = (
                    self._session.extra.get("token_url")
                    or f"{self._instance}/oauth_token.do"
                )
                resp = httpx.post(
                    token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self._session.extra["client_id"],
                        "client_secret": self._session.extra["client_secret"],
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                token_data = resp.json()
                self._session.token = token_data["access_token"]
                self._session.headers["Authorization"] = f"Bearer {self._session.token}"
                self._session.expires_at = time.time() + token_data.get("expires_in", 3600)

            self._http_client = httpx.Client(
                headers={
                    **self._session.headers,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=60,
            )
            self.status = ConnectorStatus.CONNECTED
            return True

        except ImportError:
            raise ImportError("httpx not installed. Run: pip install httpx")
        except Exception as e:
            self.status = ConnectorStatus.ERROR
            raise ConnectionError(f"ServiceNow auth failed: {e}")

    def validate_connection(self) -> HealthCheck:
        start = time.time()
        try:
            if self._http_client is None:
                self.authenticate()

            # Test with a lightweight table query
            resp = self._http_client.get(
                f"{self._instance}/api/now/table/{self._table}",
                params={"sysparm_limit": 1, "sysparm_fields": "sys_id"},
            )
            latency = (time.time() - start) * 1000

            if resp.status_code == 200:
                return HealthCheck(healthy=True, latency_ms=round(latency, 1),
                                 message=f"Connected to {self._table}")
            elif resp.status_code == 401:
                return HealthCheck(healthy=False, message="Authentication failed (401)")
            elif resp.status_code == 403:
                return HealthCheck(healthy=False, message="Insufficient permissions (403)")
            else:
                return HealthCheck(healthy=False,
                                 message=f"HTTP {resp.status_code}: {resp.text[:200]}")

        except Exception as e:
            return HealthCheck(healthy=False, message=str(e))

    def push_batch(self, records: list[dict], **kwargs) -> PushResult:
        table = kwargs.get("table", self._table)
        api_mode = kwargs.get("api_mode", self._api_mode)
        start = time.time()
        sent, failed, errors = 0, 0, []

        try:
            if self._http_client is None:
                self.authenticate()

            if api_mode == "import_set":
                return self._push_import_set(records, table)
            elif api_mode == "event":
                return self._push_events(records)
            else:
                # Table API — one record at a time (ServiceNow Table API limitation)
                for record in records:
                    try:
                        # Remove internal fields
                        clean = {k: v for k, v in record.items()
                                if not k.startswith("_") and v is not None}

                        resp = self._http_client.post(
                            f"{self._instance}/api/now/table/{table}",
                            json=clean,
                        )

                        if resp.status_code in (200, 201):
                            sent += 1
                        else:
                            failed += 1
                            if len(errors) < 10:
                                errors.append(
                                    f"HTTP {resp.status_code}: {resp.text[:200]}"
                                )
                    except Exception as e:
                        failed += 1
                        if len(errors) < 10:
                            errors.append(str(e))

        except Exception as e:
            errors.append(f"Batch error: {e}")

        return PushResult(
            success=failed == 0,
            records_sent=sent,
            records_failed=failed,
            errors=errors,
            duration_seconds=round(time.time() - start, 3),
            metadata={"table": table, "api_mode": api_mode},
        )

    def _push_import_set(self, records: list[dict], table: str) -> PushResult:
        """Push via Import Set API for bulk operations."""
        start = time.time()
        import_set_table = f"u_import_{table}"
        sent, failed, errors = 0, 0, []

        for record in records:
            try:
                clean = {k: v for k, v in record.items()
                        if not k.startswith("_") and v is not None}
                resp = self._http_client.post(
                    f"{self._instance}/api/now/import/{import_set_table}",
                    json=clean,
                )
                if resp.status_code in (200, 201):
                    sent += 1
                else:
                    failed += 1
                    if len(errors) < 10:
                        errors.append(f"Import API {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                failed += 1
                if len(errors) < 10:
                    errors.append(str(e))

        return PushResult(
            success=failed == 0,
            records_sent=sent,
            records_failed=failed,
            errors=errors,
            duration_seconds=round(time.time() - start, 3),
            metadata={"api_mode": "import_set", "import_table": import_set_table},
        )

    def _push_events(self, records: list[dict]) -> PushResult:
        """Push via Event API for Event Management."""
        start = time.time()
        sent, failed, errors = 0, 0, []

        for record in records:
            try:
                event = {
                    "source": record.get("source", "GenForge"),
                    "node": record.get("node", record.get("cmdb_ci", "")),
                    "type": record.get("type", record.get("category", "Test")),
                    "resource": record.get("resource", ""),
                    "metric_name": record.get("metric_name", ""),
                    "severity": record.get("severity", record.get("priority", 4)),
                    "description": record.get("description", record.get("short_description", "")),
                    "additional_info": json.dumps({
                        k: v for k, v in record.items()
                        if k not in ("source", "node", "type", "resource",
                                    "metric_name", "severity", "description")
                        and not k.startswith("_") and v is not None
                    }),
                }
                resp = self._http_client.post(
                    f"{self._instance}/api/global/em/jsonv2",
                    json={"records": [event]},
                )
                if resp.status_code in (200, 201):
                    sent += 1
                else:
                    failed += 1
                    if len(errors) < 10:
                        errors.append(f"Event API {resp.status_code}")
            except Exception as e:
                failed += 1
                if len(errors) < 10:
                    errors.append(str(e))

        return PushResult(
            success=failed == 0,
            records_sent=sent,
            records_failed=failed,
            errors=errors,
            duration_seconds=round(time.time() - start, 3),
            metadata={"api_mode": "event"},
        )

    def get_target_schema(self) -> dict | None:
        """Auto-detect schema from ServiceNow table metadata."""
        try:
            resp = self._http_client.get(
                f"{self._instance}/api/now/table/sys_dictionary",
                params={
                    "sysparm_query": f"name={self._table}^internal_type!=collection",
                    "sysparm_fields": "element,internal_type,max_length,mandatory",
                    "sysparm_limit": 200,
                },
            )
            if resp.status_code != 200:
                return None

            result = resp.json().get("result", [])
            snow_to_json = {
                "string": "string", "integer": "integer", "boolean": "boolean",
                "decimal": "number", "float": "number", "glide_date_time": "string",
                "reference": "string", "sys_class_name": "string",
                "journal": "string", "journal_input": "string",
            }

            properties = {}
            for field_def in result:
                name = field_def.get("element", "")
                if not name or name.startswith("sys_"):
                    continue
                internal_type = field_def.get("internal_type", "string")
                json_type = snow_to_json.get(internal_type, "string")
                prop: dict[str, Any] = {"type": json_type}
                if internal_type == "glide_date_time":
                    prop["format"] = "date-time"
                elif internal_type == "reference":
                    prop["format"] = "uuid"
                properties[name] = prop

            return {"type": "object", "properties": properties} if properties else None

        except Exception:
            return None

    def close(self):
        if self._http_client:
            self._http_client.close()
            self._http_client = None
        super().close()
