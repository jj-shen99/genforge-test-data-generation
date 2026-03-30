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

    def get_target_schema(self) -> dict | None:
        """Auto-detect schema by sampling documents from the MongoDB collection."""
        try:
            if self._db is None:
                self.authenticate()
            coll = self._db[self._collection]
            sample = list(coll.find({}, {"_id": 0}).limit(50))
            if not sample:
                return None

            # Infer types from sampled documents
            field_types: dict[str, set] = {}
            for doc in sample:
                for key, val in doc.items():
                    if key.startswith("_"):
                        continue
                    field_types.setdefault(key, set())
                    if isinstance(val, bool):
                        field_types[key].add("boolean")
                    elif isinstance(val, int):
                        field_types[key].add("integer")
                    elif isinstance(val, float):
                        field_types[key].add("number")
                    elif isinstance(val, str):
                        field_types[key].add("string")
                    elif isinstance(val, list):
                        field_types[key].add("array")
                    elif isinstance(val, dict):
                        field_types[key].add("object")
                    elif val is None:
                        pass  # skip nulls for type inference

            properties = {}
            for name, types in field_types.items():
                types.discard("object")  # prefer concrete types
                if not types:
                    properties[name] = {"type": "string"}
                elif len(types) == 1:
                    properties[name] = {"type": next(iter(types))}
                else:
                    # Multiple types seen — pick the most common
                    if "string" in types:
                        properties[name] = {"type": "string"}
                    elif "number" in types:
                        properties[name] = {"type": "number"}
                    else:
                        properties[name] = {"type": next(iter(types))}

            return {"type": "object", "properties": properties} if properties else None
        except Exception:
            return None

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
        super().close()
