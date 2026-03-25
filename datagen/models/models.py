"""Pydantic models for the GenForge API."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AuthMethodEnum(str, Enum):
    BASIC = "basic"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    BEARER_TOKEN = "bearer_token"
    AWS_IAM = "aws_iam"
    MTLS = "mtls"


# --- Schema models ---

class SchemaCreateRequest(BaseModel):
    name: str
    description: str = ""
    schema_def: dict = Field(..., alias="schema")
    category: str = "custom"
    tags: list[str] = []


class SchemaResponse(BaseModel):
    id: str
    name: str
    description: str
    schema_def: dict = Field(..., alias="schema")
    category: str
    tags: list[str]
    created_at: str
    updated_at: str


# --- Connection models ---

class ConnectionCreateRequest(BaseModel):
    name: str
    connector_type: str
    host: str
    port: int | None = None
    auth_method: AuthMethodEnum = AuthMethodEnum.BASIC
    credentials: dict[str, str] = {}
    options: dict[str, Any] = {}
    environment: str = "development"


class ConnectionResponse(BaseModel):
    id: str
    name: str
    connector_type: str
    host: str
    port: int | None
    auth_method: str
    options: dict[str, Any]
    environment: str
    status: str = "unknown"
    last_health_check: str | None = None
    created_at: str


class ConnectionTestResult(BaseModel):
    healthy: bool
    latency_ms: float = 0
    message: str = ""


# --- Job models ---

class JobCreateRequest(BaseModel):
    schema_id: str
    connection_id: str
    count: int = 100
    batch_size: int = 500
    options: dict[str, Any] = {}


class PipelineJobRequest(BaseModel):
    name: str
    steps: list[JobCreateRequest]


class JobResponse(BaseModel):
    id: str
    schema_id: str
    connection_id: str
    status: JobStatus
    count: int
    records_sent: int = 0
    records_failed: int = 0
    progress_pct: float = 0
    errors: list[str] = []
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None


# --- Generation models ---

class GenerateRequest(BaseModel):
    schema_def: dict = Field(..., alias="schema")
    count: int = 10
    output_format: str = "json"  # json, csv, jsonl


class GenerateResponse(BaseModel):
    records: list[dict]
    count: int
    duration_ms: float


# --- Dashboard models ---

class DashboardStats(BaseModel):
    total_schemas: int
    total_connections: int
    total_jobs: int
    records_generated: int
    active_jobs: int
    connectors_available: list[dict]
