"""AWS DynamoDB connector — push items via BatchWriteItem."""

from __future__ import annotations

import time

from datagen.connectors.base import (
    AuthMethod, BaseConnector, ConnectionConfig,
    ConnectorStatus, HealthCheck, PushResult,
)
from datagen.connectors.registry import register_connector


@register_connector
class AWSDynamoDBConnector(BaseConnector):
    CONNECTOR_TYPE = "aws_dynamodb"
    DISPLAY_NAME = "AWS DynamoDB"
    SUPPORTED_AUTH = [AuthMethod.AWS_IAM, AuthMethod.API_KEY]
    CATEGORY = "cloud"

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._resource = None
        self._table_name = config.options.get("table", "test_data")

    def authenticate(self) -> bool:
        try:
            import boto3
            kwargs = {}
            if self.config.auth:
                creds = self.config.auth.credentials
                kwargs["aws_access_key_id"] = creds.get("access_key")
                kwargs["aws_secret_access_key"] = creds.get("secret_key")
                kwargs["region_name"] = creds.get("region", "us-east-1")
            if self.config.host and "amazonaws" not in self.config.host:
                kwargs["endpoint_url"] = f"http://{self.config.host}:{self.config.port or 8000}"
            self._resource = boto3.resource("dynamodb", **kwargs)
            self.status = ConnectorStatus.CONNECTED
            return True
        except ImportError:
            raise ImportError("boto3 not installed. Run: pip install boto3")
        except Exception as e:
            self.status = ConnectorStatus.ERROR
            raise ConnectionError(f"DynamoDB connection failed: {e}")

    def validate_connection(self) -> HealthCheck:
        start = time.time()
        try:
            if self._resource is None:
                self.authenticate()
            table = self._resource.Table(self._table_name)
            table.load()
            latency = (time.time() - start) * 1000
            return HealthCheck(
                healthy=True, latency_ms=round(latency, 1),
                message=f"Table '{self._table_name}' ({table.item_count} items)",
            )
        except Exception as e:
            return HealthCheck(healthy=False, message=str(e))

    def push_batch(self, records: list[dict], **kwargs) -> PushResult:
        start = time.time()
        table_name = kwargs.get("table", self._table_name)
        sent, failed, errors = 0, 0, []

        try:
            if self._resource is None:
                self.authenticate()
            table = self._resource.Table(table_name)

            # DynamoDB BatchWriteItem supports max 25 items per batch
            batch_size = 25
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                try:
                    with table.batch_writer() as writer:
                        for item in batch:
                            clean = {k: v for k, v in item.items()
                                    if v is not None and not k.startswith("_")}
                            writer.put_item(Item=clean)
                    sent += len(batch)
                except Exception as e:
                    failed += len(batch)
                    if len(errors) < 5:
                        errors.append(str(e))

        except Exception as e:
            errors.append(f"Batch error: {e}")

        return PushResult(
            success=failed == 0,
            records_sent=sent, records_failed=failed, errors=errors,
            duration_seconds=round(time.time() - start, 3),
        )

    def close(self):
        self._resource = None
        super().close()
