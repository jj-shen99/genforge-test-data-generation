"""AWS S3 connector — upload generated data as objects."""

from __future__ import annotations

import io
import json
import time
from datetime import datetime, timezone

from datagen.connectors.base import (
    AuthMethod, BaseConnector, ConnectionConfig,
    ConnectorStatus, HealthCheck, PushResult,
)
from datagen.connectors.registry import register_connector


@register_connector
class AWSS3Connector(BaseConnector):
    CONNECTOR_TYPE = "aws_s3"
    DISPLAY_NAME = "AWS S3"
    SUPPORTED_AUTH = [AuthMethod.AWS_IAM, AuthMethod.API_KEY]
    CATEGORY = "cloud"

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._client = None
        self._bucket = config.options.get("bucket", "genforge-output")
        self._prefix = config.options.get("prefix", "generated/")
        self._format = config.options.get("format", "jsonl")  # jsonl, json, csv

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
            if self.config.host and self.config.host != "s3.amazonaws.com":
                kwargs["endpoint_url"] = f"https://{self.config.host}"
            self._client = boto3.client("s3", **kwargs)
            self.status = ConnectorStatus.CONNECTED
            return True
        except ImportError:
            raise ImportError("boto3 not installed. Run: pip install boto3")
        except Exception as e:
            self.status = ConnectorStatus.ERROR
            raise ConnectionError(f"AWS S3 connection failed: {e}")

    def validate_connection(self) -> HealthCheck:
        start = time.time()
        try:
            if self._client is None:
                self.authenticate()
            self._client.head_bucket(Bucket=self._bucket)
            latency = (time.time() - start) * 1000
            return HealthCheck(healthy=True, latency_ms=round(latency, 1),
                             message=f"Bucket '{self._bucket}' accessible")
        except Exception as e:
            return HealthCheck(healthy=False, message=str(e))

    def push_batch(self, records: list[dict], **kwargs) -> PushResult:
        start = time.time()
        bucket = kwargs.get("bucket", self._bucket)
        fmt = kwargs.get("format", self._format)
        prefix = kwargs.get("prefix", self._prefix)

        try:
            if self._client is None:
                self.authenticate()

            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            ext = {"jsonl": "jsonl", "json": "json", "csv": "csv"}.get(fmt, "jsonl")
            key = f"{prefix}{ts}.{ext}"

            if fmt == "jsonl":
                body = "\n".join(json.dumps(r, default=str) for r in records) + "\n"
                content_type = "application/x-ndjson"
            elif fmt == "json":
                body = json.dumps(records, default=str, indent=2)
                content_type = "application/json"
            elif fmt == "csv":
                if records:
                    headers = list(records[0].keys())
                    lines = [",".join(headers)]
                    for r in records:
                        lines.append(",".join(str(r.get(h, "")) for h in headers))
                    body = "\n".join(lines) + "\n"
                else:
                    body = ""
                content_type = "text/csv"
            else:
                body = json.dumps(records, default=str)
                content_type = "application/json"

            self._client.put_object(
                Bucket=bucket, Key=key,
                Body=body.encode("utf-8"),
                ContentType=content_type,
            )

            return PushResult(
                success=True, records_sent=len(records),
                duration_seconds=round(time.time() - start, 3),
                metadata={"bucket": bucket, "key": key, "format": fmt,
                          "size_bytes": len(body.encode("utf-8"))},
            )
        except Exception as e:
            return PushResult(success=False, errors=[str(e)],
                            duration_seconds=round(time.time() - start, 3))

    def close(self):
        self._client = None
        super().close()
