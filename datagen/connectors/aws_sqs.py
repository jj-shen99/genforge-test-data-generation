"""AWS SQS connector — send messages to an SQS queue."""

from __future__ import annotations

import json
import time

from datagen.connectors.base import (
    AuthMethod, BaseConnector, ConnectionConfig,
    ConnectorStatus, HealthCheck, PushResult,
)
from datagen.connectors.registry import register_connector


@register_connector
class AWSSQSConnector(BaseConnector):
    CONNECTOR_TYPE = "aws_sqs"
    DISPLAY_NAME = "AWS SQS"
    SUPPORTED_AUTH = [AuthMethod.AWS_IAM, AuthMethod.API_KEY]
    CATEGORY = "cloud"

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._client = None
        self._queue_url = config.options.get("queue_url", "")

    def authenticate(self) -> bool:
        try:
            import boto3
            kwargs = {}
            if self.config.auth:
                creds = self.config.auth.credentials
                kwargs["aws_access_key_id"] = creds.get("access_key")
                kwargs["aws_secret_access_key"] = creds.get("secret_key")
                if creds.get("session_token"):
                    kwargs["aws_session_token"] = creds["session_token"]
                kwargs["region_name"] = creds.get("region", "us-east-1")
            if self.config.host and self.config.host not in ("sqs.amazonaws.com", ""):
                kwargs["endpoint_url"] = f"https://{self.config.host}"
            self._client = boto3.client("sqs", **kwargs)
            self.status = ConnectorStatus.CONNECTED
            return True
        except ImportError:
            raise ImportError("boto3 not installed. Run: pip install boto3")
        except Exception as e:
            self.status = ConnectorStatus.ERROR
            raise ConnectionError(f"AWS SQS connection failed: {e}")

    def validate_connection(self) -> HealthCheck:
        start = time.time()
        try:
            if self._client is None:
                self.authenticate()
            resp = self._client.get_queue_attributes(
                QueueUrl=self._queue_url,
                AttributeNames=["ApproximateNumberOfMessages"],
            )
            latency = (time.time() - start) * 1000
            msg_count = resp.get("Attributes", {}).get("ApproximateNumberOfMessages", "?")
            return HealthCheck(healthy=True, latency_ms=round(latency, 1),
                             message=f"Queue accessible (~{msg_count} messages)")
        except Exception as e:
            return HealthCheck(healthy=False, message=str(e))

    def push_batch(self, records: list[dict], **kwargs) -> PushResult:
        """Send records as SQS messages. Uses send_message_batch (max 10 per call)."""
        start = time.time()
        queue_url = kwargs.get("queue_url", self._queue_url)
        sent, failed, errors = 0, 0, []

        try:
            if self._client is None:
                self.authenticate()

            # SQS batch limit is 10
            batch_size = 10
            for i in range(0, len(records), batch_size):
                chunk = records[i:i + batch_size]
                entries = [
                    {
                        "Id": str(j),
                        "MessageBody": json.dumps(record, default=str),
                    }
                    for j, record in enumerate(chunk)
                ]
                resp = self._client.send_message_batch(
                    QueueUrl=queue_url,
                    Entries=entries,
                )
                sent += len(resp.get("Successful", []))
                batch_failures = resp.get("Failed", [])
                failed += len(batch_failures)
                for f_item in batch_failures[:5]:
                    errors.append(f"{f_item.get('Code')}: {f_item.get('Message')}")

            return PushResult(
                success=failed == 0,
                records_sent=sent, records_failed=failed, errors=errors,
                duration_seconds=round(time.time() - start, 3),
                metadata={"queue_url": queue_url},
            )
        except Exception as e:
            return PushResult(success=False, records_sent=sent, errors=[str(e)],
                            duration_seconds=round(time.time() - start, 3))

    def close(self):
        self._client = None
        super().close()
