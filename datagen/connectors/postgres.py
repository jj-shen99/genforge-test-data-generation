"""PostgreSQL connector — push generated data via SQL INSERT/COPY."""

from __future__ import annotations

import json
import time
from typing import Any

from datagen.connectors.base import (
    AuthMethod, BaseConnector, ConnectionConfig,
    ConnectorStatus, HealthCheck, PushResult,
)
from datagen.connectors.registry import register_connector


@register_connector
class PostgreSQLConnector(BaseConnector):
    CONNECTOR_TYPE = "postgresql"
    DISPLAY_NAME = "PostgreSQL"
    SUPPORTED_AUTH = [AuthMethod.BASIC, AuthMethod.CERTIFICATE]
    CATEGORY = "database"

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._conn = None
        self._table = config.options.get("table", "test_data")
        self._schema = config.options.get("schema", "public")

    def authenticate(self) -> bool:
        try:
            import psycopg
            dsn = (
                f"host={self.config.host} "
                f"port={self.config.port or 5432} "
                f"dbname={self.config.options.get('database', 'postgres')} "
            )
            if self.config.auth:
                creds = self.config.auth.credentials
                dsn += f"user={creds.get('username', '')} password={creds.get('password', '')}"

            self._conn = psycopg.connect(dsn)
            self.status = ConnectorStatus.CONNECTED
            return True
        except ImportError:
            self.status = ConnectorStatus.ERROR
            raise ImportError("psycopg not installed. Run: pip install 'psycopg[binary]'")
        except Exception as e:
            self.status = ConnectorStatus.ERROR
            raise ConnectionError(f"PostgreSQL connection failed: {e}")

    def validate_connection(self) -> HealthCheck:
        start = time.time()
        try:
            if self._conn is None:
                self.authenticate()
            with self._conn.cursor() as cur:
                cur.execute("SELECT 1")
            latency = (time.time() - start) * 1000
            return HealthCheck(healthy=True, latency_ms=round(latency, 1),
                             message="Connected")
        except Exception as e:
            return HealthCheck(healthy=False, message=str(e))

    def push_batch(self, records: list[dict], **kwargs) -> PushResult:
        table = kwargs.get("table", self._table)
        start = time.time()
        sent, failed, errors = 0, 0, []

        try:
            if not records:
                return PushResult(success=True, records_sent=0)

            columns = list(records[0].keys())
            col_str = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))

            with self._conn.cursor() as cur:
                for record in records:
                    try:
                        values = [self._serialize_value(record.get(c)) for c in columns]
                        cur.execute(
                            f"INSERT INTO {self._schema}.{table} ({col_str}) VALUES ({placeholders})",
                            values,
                        )
                        sent += 1
                    except Exception as e:
                        failed += 1
                        if len(errors) < 10:
                            errors.append(str(e))

            self._conn.commit()

        except Exception as e:
            errors.append(f"Batch error: {e}")
            try:
                self._conn.rollback()
            except Exception:
                pass

        return PushResult(
            success=failed == 0,
            records_sent=sent,
            records_failed=failed,
            errors=errors,
            duration_seconds=round(time.time() - start, 3),
        )

    def get_target_schema(self) -> dict | None:
        """Auto-detect schema from PostgreSQL table metadata."""
        try:
            if self._conn is None:
                self.authenticate()
            with self._conn.cursor() as cur:
                cur.execute("""
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                """, (self._schema, self._table))
                rows = cur.fetchall()

            if not rows:
                return None

            pg_to_json = {
                "integer": "integer", "bigint": "integer", "smallint": "integer",
                "numeric": "number", "real": "number", "double precision": "number",
                "boolean": "boolean",
                "character varying": "string", "text": "string", "character": "string",
                "timestamp with time zone": "string", "timestamp without time zone": "string",
                "date": "string", "uuid": "string", "jsonb": "object", "json": "object",
            }

            properties = {}
            for col_name, data_type, nullable, default in rows:
                json_type = pg_to_json.get(data_type, "string")
                prop: dict[str, Any] = {"type": json_type}
                if data_type in ("timestamp with time zone", "timestamp without time zone"):
                    prop["format"] = "date-time"
                elif data_type == "date":
                    prop["format"] = "date"
                elif data_type == "uuid":
                    prop["format"] = "uuid"
                properties[col_name] = prop

            return {"type": "object", "properties": properties}

        except Exception:
            return None

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return value

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
        super().close()
