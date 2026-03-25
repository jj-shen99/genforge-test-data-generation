"""Trino connector — insert data via Trino REST API / DBAPI."""

from __future__ import annotations

import json
import time

from datagen.connectors.base import (
    AuthMethod, BaseConnector, ConnectionConfig,
    ConnectorStatus, HealthCheck, PushResult,
)
from datagen.connectors.registry import register_connector


@register_connector
class TrinoConnector(BaseConnector):
    CONNECTOR_TYPE = "trino"
    DISPLAY_NAME = "Trino"
    SUPPORTED_AUTH = [AuthMethod.BASIC, AuthMethod.MTLS]
    CATEGORY = "bigdata"

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._conn = None
        self._catalog = config.options.get("catalog", "hive")
        self._schema = config.options.get("schema", "default")
        self._table = config.options.get("table", "events")

    def authenticate(self) -> bool:
        try:
            import trino
            kwargs = {
                "host": self.config.host or "localhost",
                "port": self.config.port or 8080,
                "catalog": self._catalog,
                "schema": self._schema,
            }
            if self.config.auth and self.config.auth.credentials:
                creds = self.config.auth.credentials
                kwargs["user"] = creds.get("username", "genforge")
                if creds.get("password"):
                    kwargs["http_scheme"] = "https"
                    kwargs["auth"] = trino.auth.BasicAuthentication(
                        creds["username"], creds["password"]
                    )
            else:
                kwargs["user"] = "genforge"

            self._conn = trino.dbapi.connect(**kwargs)
            self.status = ConnectorStatus.CONNECTED
            return True
        except ImportError:
            raise ImportError("trino not installed. Run: pip install trino")
        except Exception as e:
            self.status = ConnectorStatus.ERROR
            raise ConnectionError(f"Trino connection failed: {e}")

    def validate_connection(self) -> HealthCheck:
        start = time.time()
        try:
            if self._conn is None:
                self.authenticate()
            cur = self._conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            latency = (time.time() - start) * 1000
            return HealthCheck(healthy=True, latency_ms=round(latency, 1),
                             message=f"Trino reachable ({self._catalog}.{self._schema})")
        except Exception as e:
            return HealthCheck(healthy=False, message=str(e))

    def push_batch(self, records: list[dict], **kwargs) -> PushResult:
        """Insert records into Trino table using parameterised INSERT statements."""
        start = time.time()
        table = kwargs.get("table", self._table)
        catalog = kwargs.get("catalog", self._catalog)
        schema = kwargs.get("schema", self._schema)
        sent, failed, errors = 0, 0, []

        try:
            if self._conn is None:
                self.authenticate()

            if not records:
                return PushResult(success=True, records_sent=0,
                                duration_seconds=0)

            columns = list(records[0].keys())
            col_list = ", ".join(columns)
            placeholders = ", ".join(["?"] * len(columns))
            sql = f"INSERT INTO {catalog}.{schema}.{table} ({col_list}) VALUES ({placeholders})"

            cur = self._conn.cursor()
            for record in records:
                try:
                    values = []
                    for c in columns:
                        v = record.get(c)
                        if isinstance(v, (dict, list)):
                            v = json.dumps(v, default=str)
                        values.append(v)
                    cur.execute(sql, values)
                    sent += 1
                except Exception as e:
                    failed += 1
                    if len(errors) < 5:
                        errors.append(str(e)[:200])

            return PushResult(
                success=failed == 0,
                records_sent=sent, records_failed=failed, errors=errors,
                duration_seconds=round(time.time() - start, 3),
                metadata={"table": f"{catalog}.{schema}.{table}"},
            )
        except Exception as e:
            return PushResult(success=False, errors=[str(e)],
                            duration_seconds=round(time.time() - start, 3))

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
        super().close()
