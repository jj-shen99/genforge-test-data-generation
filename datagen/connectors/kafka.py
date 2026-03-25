"""Apache Kafka connector — produce messages via confluent-kafka."""

from __future__ import annotations

import json
import time
from typing import Any, Iterator

from datagen.connectors.base import (
    AuthMethod, BaseConnector, ConnectionConfig,
    ConnectorStatus, HealthCheck, PushResult,
)
from datagen.connectors.registry import register_connector


@register_connector
class KafkaConnector(BaseConnector):
    CONNECTOR_TYPE = "kafka"
    DISPLAY_NAME = "Apache Kafka"
    SUPPORTED_AUTH = [AuthMethod.BASIC, AuthMethod.MTLS, AuthMethod.API_KEY]
    CATEGORY = "bigdata"

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._producer = None
        self._topic = config.options.get("topic", "test-data")
        self._key_field = config.options.get("key_field")

    def authenticate(self) -> bool:
        try:
            from confluent_kafka import Producer
            conf = {
                "bootstrap.servers": f"{self.config.host}:{self.config.port or 9092}",
                "client.id": "genforge-producer",
                "linger.ms": 50,
                "batch.num.messages": 1000,
                "compression.type": self.config.options.get("compression", "snappy"),
            }
            if self.config.auth:
                creds = self.config.auth.credentials
                if self.config.auth.method == AuthMethod.BASIC:
                    conf["security.protocol"] = "SASL_SSL"
                    conf["sasl.mechanisms"] = "PLAIN"
                    conf["sasl.username"] = creds.get("username", "")
                    conf["sasl.password"] = creds.get("password", "")
                elif self.config.auth.method == AuthMethod.MTLS:
                    conf["security.protocol"] = "SSL"
                    conf["ssl.certificate.location"] = creds.get("cert_path", "")
                    conf["ssl.key.location"] = creds.get("key_path", "")
                    conf["ssl.ca.location"] = creds.get("ca_path", "")
            self._producer = Producer(conf)
            self.status = ConnectorStatus.CONNECTED
            return True
        except ImportError:
            raise ImportError("confluent-kafka not installed. Run: pip install confluent-kafka")
        except Exception as e:
            self.status = ConnectorStatus.ERROR
            raise ConnectionError(f"Kafka connection failed: {e}")

    def validate_connection(self) -> HealthCheck:
        start = time.time()
        try:
            if self._producer is None:
                self.authenticate()
            metadata = self._producer.list_topics(timeout=10)
            latency = (time.time() - start) * 1000
            topics = list(metadata.topics.keys())
            return HealthCheck(
                healthy=True, latency_ms=round(latency, 1),
                message=f"{len(topics)} topics available",
                details={"topics": topics[:20]},
            )
        except Exception as e:
            return HealthCheck(healthy=False, message=str(e))

    def push_batch(self, records: list[dict], **kwargs) -> PushResult:
        topic = kwargs.get("topic", self._topic)
        start = time.time()
        sent, failed, errors = 0, 0, []
        delivery_errors = []

        def delivery_callback(err, msg):
            nonlocal sent, failed
            if err:
                failed += 1
                if len(delivery_errors) < 10:
                    delivery_errors.append(str(err))
            else:
                sent += 1

        try:
            if self._producer is None:
                self.authenticate()
            for record in records:
                key = None
                if self._key_field and self._key_field in record:
                    key = str(record[self._key_field]).encode("utf-8")
                value = json.dumps(record, default=str).encode("utf-8")
                self._producer.produce(
                    topic=topic, key=key, value=value,
                    callback=delivery_callback,
                )
                self._producer.poll(0)
            self._producer.flush(timeout=30)
            errors = delivery_errors
        except Exception as e:
            errors.append(str(e))

        return PushResult(
            success=failed == 0,
            records_sent=sent, records_failed=failed, errors=errors,
            duration_seconds=round(time.time() - start, 3),
            metadata={"topic": topic},
        )

    def push_stream(self, records: Iterator[dict], **kwargs) -> PushResult:
        """True streaming mode for Kafka — produce as records arrive."""
        topic = kwargs.get("topic", self._topic)
        start = time.time()
        sent, failed = 0, 0

        try:
            if self._producer is None:
                self.authenticate()
            for record in records:
                key = None
                if self._key_field and self._key_field in record:
                    key = str(record[self._key_field]).encode("utf-8")
                value = json.dumps(record, default=str).encode("utf-8")
                self._producer.produce(topic=topic, key=key, value=value)
                sent += 1
                if sent % 1000 == 0:
                    self._producer.poll(0)
            self._producer.flush(timeout=30)
        except Exception as e:
            return PushResult(success=False, records_sent=sent, errors=[str(e)],
                            duration_seconds=round(time.time() - start, 3))

        return PushResult(
            success=True, records_sent=sent,
            duration_seconds=round(time.time() - start, 3),
            metadata={"topic": topic},
        )

    def close(self):
        if self._producer:
            self._producer.flush(timeout=5)
            self._producer = None
        super().close()
