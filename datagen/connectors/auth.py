"""
Authentication provider implementations.

Handles OAuth2 token exchange, API key injection, AWS SigV4 signing,
mTLS setup, and other auth flows used by connectors.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from datagen.connectors.base import AuthConfig, AuthMethod


@dataclass
class AuthSession:
    """Active authentication session with token/credential state."""
    method: AuthMethod
    headers: dict[str, str]
    params: dict[str, str] | None = None
    token: str | None = None
    expires_at: float | None = None  # Unix timestamp
    extra: dict[str, Any] | None = None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at - 30  # 30s buffer


class AuthProvider:
    """Factory for creating auth sessions from config."""

    @staticmethod
    def create_session(auth: AuthConfig) -> AuthSession:
        """Create an auth session from config."""
        if auth.method == AuthMethod.BASIC:
            return AuthProvider._basic_auth(auth)
        elif auth.method == AuthMethod.API_KEY:
            return AuthProvider._api_key_auth(auth)
        elif auth.method == AuthMethod.BEARER_TOKEN:
            return AuthProvider._bearer_auth(auth)
        elif auth.method == AuthMethod.OAUTH2:
            return AuthProvider._oauth2_auth(auth)
        elif auth.method == AuthMethod.AWS_IAM:
            return AuthProvider._aws_iam_auth(auth)
        else:
            return AuthSession(method=auth.method, headers={})

    @staticmethod
    def _basic_auth(auth: AuthConfig) -> AuthSession:
        username = auth.credentials.get("username", "")
        password = auth.credentials.get("password", "")
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
        return AuthSession(
            method=AuthMethod.BASIC,
            headers={"Authorization": f"Basic {encoded}"},
        )

    @staticmethod
    def _api_key_auth(auth: AuthConfig) -> AuthSession:
        key = auth.credentials.get("key", "")
        header = auth.credentials.get("header", "X-API-Key")
        prefix = auth.credentials.get("prefix", "")
        value = f"{prefix}{key}" if prefix else key

        # Some APIs use query params instead of headers
        if auth.credentials.get("in") == "query":
            param_name = auth.credentials.get("param_name", "api_key")
            return AuthSession(
                method=AuthMethod.API_KEY,
                headers={},
                params={param_name: key},
            )

        return AuthSession(
            method=AuthMethod.API_KEY,
            headers={header: value},
        )

    @staticmethod
    def _bearer_auth(auth: AuthConfig) -> AuthSession:
        token = auth.credentials.get("token", "")
        return AuthSession(
            method=AuthMethod.BEARER_TOKEN,
            headers={"Authorization": f"Bearer {token}"},
            token=token,
        )

    @staticmethod
    def _oauth2_auth(auth: AuthConfig) -> AuthSession:
        """OAuth2 client credentials flow.

        In production, this would make an HTTP request to the token URL.
        Here we prepare the session structure for integration.
        """
        client_id = auth.credentials.get("client_id", "")
        client_secret = auth.credentials.get("client_secret", "")
        token_url = auth.credentials.get("token_url", "")
        scope = auth.credentials.get("scope", "")

        # In real implementation, this would call:
        # POST {token_url} with client_id, client_secret, grant_type=client_credentials
        # For now, return a placeholder session structure
        return AuthSession(
            method=AuthMethod.OAUTH2,
            headers={},  # Will be populated after token exchange
            extra={
                "client_id": client_id,
                "client_secret": client_secret,
                "token_url": token_url,
                "scope": scope,
                "grant_type": "client_credentials",
            },
        )

    @staticmethod
    def _aws_iam_auth(auth: AuthConfig) -> AuthSession:
        """AWS IAM authentication.

        In production, this uses boto3 / botocore for SigV4 signing.
        """
        return AuthSession(
            method=AuthMethod.AWS_IAM,
            headers={},
            extra={
                "access_key": auth.credentials.get("access_key", ""),
                "secret_key": auth.credentials.get("secret_key", ""),
                "region": auth.credentials.get("region", "us-east-1"),
                "role_arn": auth.credentials.get("role_arn"),
                "session_token": auth.credentials.get("session_token"),
            },
        )


def refresh_oauth2_token(session: AuthSession) -> AuthSession:
    """Refresh an OAuth2 token. Placeholder for HTTP integration."""
    if session.extra and session.extra.get("token_url"):
        # In production: POST to token_url, get new access_token
        # For now, return the existing session
        pass
    return session
