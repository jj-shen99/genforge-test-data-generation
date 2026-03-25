"""AWS Kinesis connector — put records into a Kinesis data stream."""

from __future__ import annotations

import json
import time

from datagen.connectors.base import (
    AuthMethod, BaseConnector, ConnectionConfig,
    ConnectorStatus, HealthCheck, PushResult,
)
from datagen.connectors.registry import register_connector


@register_connector
class AWSKinesisConnector(BaseConnector):
    CONNECTOR_TYPE = "aws_kinesis"
    DISPLAY_NAME = "AWS Kinesis"
    SUPPORTED_AUTH = [AuthMethod.AWS_IAM, AuthMethod.API_KEY]
    CATEGORY = "cloud"

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._client = None
        self._stream_name = config.options.get("stream_name", "genforge-stream")
        self._partition_key_field = config.options.get("partition_key_field")

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
            if self.config.host and self.config.host not in ("kinesis.amazonaws.com", ""):
                kwargs["endpoint_url"] = f"https://{self.config.host}"
            self._client = boto3.client("kinesis", **kwargs)
            self.status = ConnectorStatus.CONNECTED
            return True
        except ImportError:
            raise ImportError("boto3 not installed. Run: pip install boto3")
        except Exception as e:
            self.status = ConnectorStatus.ERROR
            raise ConnectionError(f"AWS Kinesis connection failed: {e}")

    def validate_connection(self) -> HealthCheck:
        start = time.time()
        try:
            if self._client is None:
                self.authenticate()
            resp = self._client.describe_stream_summary(
                StreamName=self._stream_name
            )
            latency = (time.time() - start) * 1000
            summary = resp.get("StreamDescriptionSummary", {})
            status = summary.get("StreamStatus", "UNKNOWN")
            shards = summary.get("OpenShardCount", "?")
            return HealthCheck(healthy=status == "ACTIVE",
                             latency_ms=round(latency, 1),
                             message=f"Stream '{self._stream_name}': {status} ({shards} shards)")
        except Exception as e:
            return HealthCheck(healthy=False, message=str(e))

    def push_batch(self, records: list[dict], **kwargs) -> PushResult:
        """Put records into Kinesis using put_records (max 500 per call)."""
        start = time.time()
        stream = kwargs.get("stream_name", self._stream_name)
        sent, failed, errors = 0, 0, []

        try:
            if self._client is None:
                self.authenticate()

            batch_size = 500  # Kinesis limit
            for i in range(0, len(records), batch_size):
                chunk = records[i:i + batch_size]
                entries = []
                for record in chunk:
                    pk = str(record.get(self._partition_key_field, str(time.time()))) \
                        if self._partition_key_field else str(time.time())
                    entries.append({
                        "Data": json.dumps(record, default=str).encode("utf-8"),
                        "PartitionKey": pk,
                    })

                resp = self._client.put_records(
                    StreamName=stream,
                    Records=entries,
                )
                fail_count = resp.get("FailedRecordCount", 0)
                sent += len(entries) - fail_count
                failed += fail_count

                if fail_count > 0:
                    for j, rec_resp in enumerate(resp.get("Records", [])):
                        if rec_resp.get("ErrorCode"):
                            if len(errors) < 5:
                                errors.append(f"{rec_resp['ErrorCode']}: {rec_resp.get('ErrorMessage', '')}")

            return PushResult(
                success=failed == 0,
                records_sent=sent, records_failed=failed, errors=errors,
                duration_seconds=round(time.time() - start, 3),
                metadata={"stream": stream},
            )
        except Exception as e:
            return PushResult(success=False, records_sent=sent, errors=[str(e)],
                            duration_seconds=round(time.time() - start, 3))

    def close(self):
        self._client = None
        super().close()
