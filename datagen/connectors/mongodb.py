"""MongoDB connector — push documents via insertMany."""

from __future__ import annotations

import time

from datagen.connectors.base import (
    AuthMethod, BaseConnector, ConnectionConfig,
    ConnectorStatus, HealthCheck, PushResult,
)
from datagen.connectors.registry import register_connector


@register_connector
class MongoDBConnector(BaseConnector):
    CONNECTOR_TYPE = "mongodb"
    DISPLAY_NAME = "MongoDB"
    SUPPORTED_AUTH = [AuthMethod.BASIC, AuthMethod.CERTIFICATE]
    CATEGORY = "database"

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._client = None
        self._db = None
        self._database = config.options.get("database", "test")
        self._collection = config.options.get("collection", "test_data")

    def authenticate(self) -> bool:
        try:
            from pymongo import MongoClient
            port = self.config.port or 27017
            uri = self.config.options.get("uri")
            if uri:
                self._client = MongoClient(uri)
            else:
                kwargs = {"host": self.config.host, "port": port}
                if self.config.auth:
                    creds = self.config.auth.credentials
                    kwargs["username"] = creds.get("username")
                    kwargs["password"] = creds.get("password")
                    kwargs["authSource"] = self.config.options.get("auth_source", "admin")
                self._client = MongoClient(**kwargs)
            self._db = self._client[self._database]
            self.status = ConnectorStatus.CONNECTED
            return True
        except ImportError:
            raise ImportError("pymongo not installed. Run: pip install pymongo")
        except Exception as e:
            self.status = ConnectorStatus.ERROR
            raise ConnectionError(f"MongoDB connection failed: {e}")

    def validate_connection(self) -> HealthCheck:
        start = time.time()
        try:
            if self._client is None:
                self.authenticate()
            self._client.admin.command("ping")
            latency = (time.time() - start) * 1000
            return HealthCheck(healthy=True, latency_ms=round(latency, 1),
                             message=f"Connected to {self._database}")
        except Exception as e:
            return HealthCheck(healthy=False, message=str(e))

    def push_batch(self, records: list[dict], **kwargs) -> PushResult:
        collection = kwargs.get("collection", self._collection)
        start = time.time()
        try:
            if self._db is None:
                self.authenticate()
            coll = self._db[collection]
            result = coll.insert_many(records, ordered=False)
            return PushResult(
                success=True,
                records_sent=len(result.inserted_ids),
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
