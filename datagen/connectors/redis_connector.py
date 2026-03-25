"""Redis connector — push data as keys, hashes, or list entries."""

from __future__ import annotations

import json
import time

from datagen.connectors.base import (
    AuthMethod, BaseConnector, ConnectionConfig,
    ConnectorStatus, HealthCheck, PushResult,
)
from datagen.connectors.registry import register_connector


@register_connector
class RedisConnector(BaseConnector):
    CONNECTOR_TYPE = "redis"
    DISPLAY_NAME = "Redis"
    SUPPORTED_AUTH = [AuthMethod.BASIC, AuthMethod.API_KEY]
    CATEGORY = "database"

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._client = None
        self._key_prefix = config.options.get("key_prefix", "genforge:")
        self._data_type = config.options.get("data_type", "hash")  # hash, string, list
        self._list_name = config.options.get("list_name", "genforge:records")
        self._ttl = config.options.get("ttl")  # seconds, optional

    def authenticate(self) -> bool:
        try:
            import redis as redis_lib
            password = None
            username = None
            if self.config.auth and self.config.auth.credentials:
                password = self.config.auth.credentials.get("password", "")
                username = self.config.auth.credentials.get("username")
                if not password:
                    password = None
                if not username:
                    username = None

            self._client = redis_lib.Redis(
                host=self.config.host or "localhost",
                port=self.config.port or 6379,
                password=password,
                username=username,
                db=self.config.options.get("db", 0),
                ssl=self.config.options.get("ssl", False),
                decode_responses=True,
                socket_timeout=10,
            )
            self._client.ping()
            self.status = ConnectorStatus.CONNECTED
            return True
        except ImportError:
            raise ImportError("redis not installed. Run: pip install redis")
        except Exception as e:
            self.status = ConnectorStatus.ERROR
            raise ConnectionError(f"Redis connection failed: {e}")

    def validate_connection(self) -> HealthCheck:
        start = time.time()
        try:
            if self._client is None:
                self.authenticate()
            info = self._client.info("server")
            latency = (time.time() - start) * 1000
            version = info.get("redis_version", "unknown")
            return HealthCheck(healthy=True, latency_ms=round(latency, 1),
                             message=f"Redis {version} reachable",
                             details={"version": version})
        except Exception as e:
            return HealthCheck(healthy=False, message=str(e))

    def push_batch(self, records: list[dict], **kwargs) -> PushResult:
        start = time.time()
        sent, failed, errors = 0, 0, []
        data_type = kwargs.get("data_type", self._data_type)

        try:
            if self._client is None:
                self.authenticate()

            pipe = self._client.pipeline()

            for i, record in enumerate(records):
                try:
                    key = f"{self._key_prefix}{int(time.time()*1000)}:{i}"
                    if data_type == "hash":
                        flat = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                                for k, v in record.items()}
                        pipe.hset(key, mapping=flat)
                    elif data_type == "string":
                        pipe.set(key, json.dumps(record, default=str))
                    elif data_type == "list":
                        pipe.rpush(self._list_name, json.dumps(record, default=str))
                        key = self._list_name
                    else:
                        pipe.set(key, json.dumps(record, default=str))

                    if self._ttl and data_type != "list":
                        pipe.expire(key, self._ttl)
                    sent += 1
                except Exception as e:
                    failed += 1
                    if len(errors) < 5:
                        errors.append(str(e))

            pipe.execute()

            return PushResult(
                success=failed == 0,
                records_sent=sent, records_failed=failed, errors=errors,
                duration_seconds=round(time.time() - start, 3),
                metadata={"data_type": data_type, "key_prefix": self._key_prefix},
            )
        except Exception as e:
            return PushResult(success=False, errors=[str(e)],
                            duration_seconds=round(time.time() - start, 3))

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
        super().close()
