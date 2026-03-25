"""
Abstract base class for all GenForge connectors.

Every connector implements this interface to provide:
- Authentication
- Connection validation
- Batch push
- Streaming push
- Schema auto-detection
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Iterator


class ConnectorStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"


class AuthMethod(Enum):
    BASIC = "basic"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    BEARER_TOKEN = "bearer_token"
    AWS_IAM = "aws_iam"
    MTLS = "mtls"
    KERBEROS = "kerberos"
    SAML = "saml"
    SSH_KEY = "ssh_key"
    CERTIFICATE = "certificate"


@dataclass
class AuthConfig:
    """Authentication configuration."""
    method: AuthMethod
    credentials: dict[str, str] = field(default_factory=dict)
    # Common fields:
    #   basic: {"username": "...", "password": "..."}
    #   api_key: {"key": "...", "header": "X-API-Key"}
    #   oauth2: {"client_id": "...", "client_secret": "...", "token_url": "..."}
    #   bearer_token: {"token": "..."}
    #   aws_iam: {"access_key": "...", "secret_key": "...", "region": "...", "role_arn": "..."}
    #   mtls: {"cert_path": "...", "key_path": "...", "ca_path": "..."}


@dataclass
class ConnectionConfig:
    """Target application connection configuration."""
    name: str
    connector_type: str
    host: str
    port: int | None = None
    auth: AuthConfig | None = None
    options: dict[str, Any] = field(default_factory=dict)
    # Connector-specific options go here
    # e.g. {"database": "mydb", "collection": "users"} for MongoDB
    #      {"index": "logs-2024"} for Elasticsearch
    #      {"instance": "dev12345.service-now.com", "table": "incident"} for ServiceNow


@dataclass
class PushResult:
    """Result of a push operation."""
    success: bool
    records_sent: int = 0
    records_failed: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthCheck:
    """Connection health check result."""
    healthy: bool
    latency_ms: float = 0.0
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class BaseConnector(ABC):
    """Abstract base class for GenForge connectors.

    All connectors must implement the five core methods:
    1. authenticate()  — establish auth session
    2. validate_connection() — test that the target is reachable and writable
    3. push_batch() — send a batch of records
    4. push_stream() — send records one at a time (streaming)
    5. get_target_schema() — auto-detect the target's expected schema

    Connectors should also implement:
    - close() — clean up resources
    - health_check() — lightweight connectivity check
    """

    # Connector metadata — override in subclasses
    CONNECTOR_TYPE: str = "base"
    DISPLAY_NAME: str = "Base Connector"
    SUPPORTED_AUTH: list[AuthMethod] = []
    CATEGORY: str = "generic"  # observability, database, cloud, servicenow, cicd, infra

    def __init__(self, config: ConnectionConfig):
        self.config = config
        self.status = ConnectorStatus.DISCONNECTED
        self._auth_session: Any = None

    @abstractmethod
    def authenticate(self) -> bool:
        """Establish authentication session.

        Returns True if authentication succeeded.
        Stores session tokens/credentials internally.
        """
        ...

    @abstractmethod
    def validate_connection(self) -> HealthCheck:
        """Validate that the target is reachable and the connector can write.

        Should test:
        - Network connectivity
        - Authentication validity
        - Write permissions
        - Target existence (e.g., table exists, index exists)
        """
        ...

    @abstractmethod
    def push_batch(self, records: list[dict], **kwargs) -> PushResult:
        """Push a batch of records to the target.

        Args:
            records: List of generated records to push
            **kwargs: Connector-specific options (e.g., index, table, batch_size)

        Returns:
            PushResult with success/failure details
        """
        ...

    def push_stream(self, records: Iterator[dict], **kwargs) -> PushResult:
        """Push records one at a time in streaming mode.

        Default implementation batches internally and calls push_batch.
        Override for true streaming connectors (e.g., Kafka, Kinesis).
        """
        batch_size = kwargs.pop("batch_size", 500)
        batch = []
        total_sent = 0
        total_failed = 0
        errors = []
        start = time.time()

        for record in records:
            batch.append(record)
            if len(batch) >= batch_size:
                result = self.push_batch(batch, **kwargs)
                total_sent += result.records_sent
                total_failed += result.records_failed
                errors.extend(result.errors)
                batch = []

        # Flush remaining
        if batch:
            result = self.push_batch(batch, **kwargs)
            total_sent += result.records_sent
            total_failed += result.records_failed
            errors.extend(result.errors)

        return PushResult(
            success=total_failed == 0,
            records_sent=total_sent,
            records_failed=total_failed,
            errors=errors[:20],  # Cap error list
            duration_seconds=round(time.time() - start, 3),
        )

    def get_target_schema(self) -> dict | None:
        """Auto-detect the target's expected schema.

        Returns a JSON Schema dict describing the expected record format,
        or None if auto-detection is not supported.
        """
        return None

    def health_check(self) -> HealthCheck:
        """Lightweight health check. Default delegates to validate_connection."""
        return self.validate_connection()

    def close(self):
        """Clean up resources, close connections."""
        self.status = ConnectorStatus.DISCONNECTED

    def __enter__(self):
        self.authenticate()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __repr__(self):
        return f"<{self.__class__.__name__} target={self.config.host} status={self.status.value}>"
