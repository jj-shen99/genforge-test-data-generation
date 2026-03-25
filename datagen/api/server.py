"""
GenForge API Server — FastAPI backend with REST + WebSocket.

Provides endpoints for schema management, connection management,
job orchestration, and real-time progress streaming.

Run with: uvicorn datagen.api.server:app --reload --port 3800
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from datagen.connectors.base import AuthConfig, AuthMethod, ConnectionConfig
from datagen.connectors.registry import create_connector, list_connectors
from datagen.engine.pipeline import GenerationPipeline
from datagen.engine.schema_parser import SchemaParser
from datagen.engine.timeseries import generate_log_entries, generate_metrics
from datagen.models.models import (
    ConnectionCreateRequest, ConnectionTestResult,
    GenerateRequest, GenerateResponse,
    JobCreateRequest, JobResponse, JobStatus,
    SchemaCreateRequest,
)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="GenForge",
    description="Test Data Generation Framework API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# PostgreSQL persistence
# ---------------------------------------------------------------------------

import datagen.db.database as db

_ws_clients: list[WebSocket] = []
_startup_time: float = 0.0

# Preload example schemas
_EXAMPLE_SCHEMAS_DIR = Path(__file__).parent.parent.parent / "configs" / "schemas"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())[:8]


# ---------------------------------------------------------------------------
# Authentication endpoints
# ---------------------------------------------------------------------------

@app.post("/api/auth/login")
async def login(body: dict):
    username = body.get("username", "")
    password = body.get("password", "")
    if not username or not password:
        raise HTTPException(400, "Username and password required")
    user = await db.authenticate_user(username, password)
    if not user:
        raise HTTPException(401, "Invalid username or password")
    return {"user": user, "token": f"{user['id']}:{user['role']}"}


@app.get("/api/auth/users")
async def list_users_endpoint():
    users = await db.list_users()
    return {"users": users}


@app.post("/api/auth/users")
async def create_user_endpoint(body: dict):
    username = body.get("username", "")
    password = body.get("password", "")
    role = body.get("role", "user")
    display_name = body.get("display_name", "")
    if not username or not password:
        raise HTTPException(400, "Username and password required")
    if role not in ("admin", "user"):
        raise HTTPException(400, "Role must be 'admin' or 'user'")
    user = await db.create_user(username, password, role, display_name)
    return user


@app.delete("/api/auth/users/{user_id}")
async def delete_user_endpoint(user_id: str):
    deleted = await db.delete_user(user_id)
    if not deleted:
        raise HTTPException(404, "User not found")
    return {"deleted": True}


@app.post("/api/auth/register")
async def register(body: dict):
    username = body.get("username", "").strip()
    password = body.get("password", "")
    email = body.get("email", "").strip().lower()
    display_name = body.get("display_name", "").strip()
    if not username or not password:
        raise HTTPException(400, "Username and password required")
    if len(password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if email and not _is_valid_email(email):
        raise HTTPException(400, "Invalid email address")
    if await db.check_username_exists(username):
        raise HTTPException(409, "Username already taken")
    if email and await db.check_email_exists(email):
        raise HTTPException(409, "Email already registered")
    user = await db.create_user(username, password, role="user",
                                display_name=display_name, email=email)
    return {"user": user, "token": f"{user['id']}:{user['role']}"}


@app.post("/api/auth/reset-password")
async def reset_password(body: dict):
    username = body.get("username", "").strip()
    email = body.get("email", "").strip().lower()
    new_password = body.get("new_password", "")
    if not new_password:
        raise HTTPException(400, "New password is required")
    if len(new_password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if not username and not email:
        raise HTTPException(400, "Username or email is required")
    # Look up user by username or email
    user = None
    if username:
        user = await db.get_user_by_username(username)
    if not user and email:
        user = await db.get_user_by_email(email)
    if not user:
        raise HTTPException(404, "No account found with that username or email")
    updated = await db.update_user_password(user["id"], new_password)
    if not updated:
        raise HTTPException(500, "Failed to update password")
    return {"message": "Password reset successfully", "username": user["username"]}


def _is_valid_email(email: str) -> bool:
    import re
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email))


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health_check():
    uptime = round(time.time() - _startup_time, 1) if _startup_time else 0
    stats = await db.get_stats()
    return {
        "status": "healthy",
        "version": "0.1.0",
        "uptime_seconds": uptime,
        "schemas_loaded": stats["total_schemas"],
        "active_jobs": stats["active_jobs"],
    }


# ---------------------------------------------------------------------------
# Schema endpoints
# ---------------------------------------------------------------------------

@app.get("/api/schemas")
async def list_schemas_endpoint():
    schemas = await db.list_schemas()
    return {"schemas": schemas, "total": len(schemas)}


@app.post("/api/schemas")
async def create_schema_endpoint(req: SchemaCreateRequest):
    entry = await db.create_schema(
        name=req.name,
        description=req.description,
        schema_def=req.schema_def,
        category=req.category,
        tags=req.tags,
    )
    return entry


@app.get("/api/schemas/{schema_id}")
async def get_schema_endpoint(schema_id: str):
    s = await db.get_schema(schema_id)
    if not s:
        raise HTTPException(404, "Schema not found")
    return s


@app.delete("/api/schemas/{schema_id}")
async def delete_schema_endpoint(schema_id: str):
    deleted = await db.delete_schema(schema_id)
    if not deleted:
        raise HTTPException(404, "Schema not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Connection endpoints
# ---------------------------------------------------------------------------

@app.get("/api/connections")
async def list_connections_endpoint():
    conns = await db.list_connections()
    return {"connections": conns, "total": len(conns)}


@app.post("/api/connections")
async def create_connection_endpoint(req: ConnectionCreateRequest):
    entry = await db.create_connection(
        name=req.name,
        connector_type=req.connector_type,
        host=req.host,
        port=req.port,
        auth_method=req.auth_method.value,
        credentials=req.credentials,
        options=req.options,
    )
    return entry


@app.post("/api/connections/{conn_id}/test")
async def test_connection_endpoint(conn_id: str):
    conn_data = await db.get_connection_with_creds(conn_id)
    if not conn_data:
        raise HTTPException(404, "Connection not found")

    try:
        config = ConnectionConfig(
            name=conn_data["name"],
            connector_type=conn_data["connector_type"],
            host=conn_data["host"],
            port=conn_data.get("port"),
            auth=AuthConfig(
                method=AuthMethod(conn_data["auth_method"]),
                credentials=conn_data.get("credentials", {}),
            ),
            options=conn_data.get("options", {}),
        )
        connector = create_connector(config)
        health = connector.validate_connection()
        connector.close()

        new_status = "healthy" if health.healthy else "error"
        await db.update_connection_status(conn_id, new_status)

        return ConnectionTestResult(
            healthy=health.healthy,
            latency_ms=health.latency_ms,
            message=health.message,
        )
    except Exception as e:
        await db.update_connection_status(conn_id, "error")
        return ConnectionTestResult(healthy=False, message=str(e))


@app.delete("/api/connections/{conn_id}")
async def delete_connection_endpoint(conn_id: str):
    deleted = await db.delete_connection(conn_id)
    if not deleted:
        raise HTTPException(404, "Connection not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Connector catalog
# ---------------------------------------------------------------------------

@app.get("/api/connectors")
async def get_connectors():
    return {"connectors": list_connectors()}


# ---------------------------------------------------------------------------
# Generate (preview / export — no push)
# ---------------------------------------------------------------------------

@app.post("/api/generate")
async def generate_data(req: GenerateRequest):
    start = time.time()
    try:
        parser = SchemaParser(req.schema_def)
        records = parser.generate(count=req.count)

        # Edge-case injection when requested
        include_edge_cases = False
        if hasattr(req, 'options') and req.options:
            include_edge_cases = req.options.get("include_edge_cases", False)
        if include_edge_cases and records:
            edge = _inject_edge_cases(records[0], req.schema_def)
            records.append(edge)

        duration = (time.time() - start) * 1000
        return GenerateResponse(records=records, count=len(records), duration_ms=round(duration, 1))
    except Exception as e:
        raise HTTPException(400, f"Generation error: {e}")


def _inject_edge_cases(sample: dict, schema_def: dict) -> dict:
    """Generate a record with boundary/edge-case values."""
    edge: dict[str, Any] = {}
    props = schema_def.get("properties", {})
    for field, spec in props.items():
        ftype = spec.get("type", "string")
        if ftype == "string":
            edge[field] = ""  # empty string edge case
        elif ftype == "integer":
            edge[field] = spec.get("minimum", 0)
        elif ftype == "number":
            edge[field] = spec.get("minimum", 0.0)
        elif ftype == "boolean":
            edge[field] = False
        elif ftype == "array":
            edge[field] = []
        else:
            edge[field] = None
    return edge


@app.post("/api/generate/timeseries")
async def generate_timeseries(config: dict):
    """Generate time-series data (metrics or logs)."""
    mode = config.pop("mode", "metrics")
    if mode == "logs":
        data = generate_log_entries(config)
    else:
        data = generate_metrics(config)
    return {"data": data, "count": len(data)}


# ---------------------------------------------------------------------------
# Job endpoints
# ---------------------------------------------------------------------------

@app.post("/api/jobs")
async def create_job_endpoint(req: JobCreateRequest):
    schema = await db.get_schema(req.schema_id)
    if not schema:
        raise HTTPException(404, "Schema not found")

    job = await db.create_job(
        schema_id=req.schema_id,
        connection_id=req.connection_id,
        count=req.count,
        batch_size=req.batch_size,
        options=req.options,
    )

    # Execute inline (in production: enqueue to Celery/NATS)
    await _execute_job(job["id"])

    return await db.get_job(job["id"])


async def _execute_job(job_id: str):
    """Execute a job (inline for prototype; async worker in production)."""
    await db.update_job(job_id, status=JobStatus.RUNNING.value, started_at=_now())
    job = await db.get_job(job_id)
    start = time.time()

    await _broadcast_ws({"type": "job_update", "job": job})

    records_sent = 0
    records_failed = 0
    errors = []

    try:
        schema = await db.get_schema(job["schema_id"])
        schema_data = schema["schema"]
        parser = SchemaParser(schema_data)

        # Generate all records
        records = parser.generate(count=job["count"])

        # Push if connection specified
        conn_data = None
        if job["connection_id"]:
            conn_data = await db.get_connection_with_creds(job["connection_id"])

        if conn_data:
            config = ConnectionConfig(
                name=conn_data["name"],
                connector_type=conn_data["connector_type"],
                host=conn_data["host"],
                port=conn_data.get("port"),
                auth=AuthConfig(
                    method=AuthMethod(conn_data["auth_method"]),
                    credentials=conn_data.get("credentials", {}),
                ),
                options=conn_data.get("options", {}),
            )
            connector = create_connector(config)
            connector.authenticate()

            # Push in batches
            batch_size = job["batch_size"]
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                result = connector.push_batch(batch)
                records_sent += result.records_sent
                records_failed += result.records_failed
                errors.extend(result.errors[:5])
                progress = round((i + len(batch)) / len(records) * 100, 1)
                await db.update_job(job_id, records_sent=records_sent,
                                    records_failed=records_failed, progress_pct=progress)
                await _broadcast_ws({"type": "job_progress", "job_id": job_id,
                                    "progress": progress})

            connector.close()
        else:
            # No connection — just mark generated
            records_sent = len(records)

        status = JobStatus.COMPLETED.value if records_failed == 0 else JobStatus.FAILED.value

    except Exception as e:
        status = JobStatus.FAILED.value
        errors.append(str(e))

    duration = round(time.time() - start, 3)
    await db.update_job(
        job_id,
        status=status,
        records_sent=records_sent,
        records_failed=records_failed,
        progress_pct=100,
        errors=errors,
        completed_at=_now(),
        duration_seconds=duration,
    )
    updated_job = await db.get_job(job_id)
    await _broadcast_ws({"type": "job_update", "job": updated_job})


@app.get("/api/jobs")
async def list_jobs_endpoint():
    jobs = await db.list_jobs()
    return {"jobs": jobs, "total": len(jobs)}


@app.get("/api/jobs/{job_id}")
async def get_job_endpoint(job_id: str):
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------

@app.get("/api/stats")
async def get_stats_endpoint():
    stats = await db.get_stats()
    uptime = round(time.time() - _startup_time, 1) if _startup_time else 0
    stats["uptime_seconds"] = uptime
    stats["connectors_available"] = list_connectors()
    return stats


# ---------------------------------------------------------------------------
# WebSocket for real-time updates
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    try:
        while True:
            data = await ws.receive_text()
            # Handle client messages if needed
    except WebSocketDisconnect:
        _ws_clients.remove(ws)


async def _broadcast_ws(message: dict):
    """Broadcast a message to all connected WebSocket clients."""
    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.remove(ws)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    global _startup_time
    _startup_time = time.time()

    # Initialize PostgreSQL connection pool and create tables
    await db.init_pool()

    # Seed default users (admin/admin123, user/user123)
    await db.seed_default_users()

    # Load example schemas from configs/schemas/ if they exist
    existing = await db.list_schemas()
    existing_names = {s["name"] for s in existing}
    if _EXAMPLE_SCHEMAS_DIR.exists():
        for path in _EXAMPLE_SCHEMAS_DIR.glob("*.json"):
            try:
                with open(path) as f:
                    schema = json.load(f)
                name = schema.get("title", path.stem.replace("_", " ").title())
                if name not in existing_names:
                    await db.create_schema(
                        name=name,
                        description=schema.get("description", ""),
                        schema_def=schema,
                        category=schema.get("x-datagen-category", "custom"),
                        tags=schema.get("x-datagen-tags", []),
                    )
            except Exception:
                pass


@app.on_event("shutdown")
async def shutdown():
    await db.close_pool()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3800)
