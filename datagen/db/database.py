"""
GenForge PostgreSQL database layer.

Provides async connection pool, table creation, and CRUD operations
for schemas, connections, and jobs.

Requires: psycopg[binary] >= 3.1  (pip install 'psycopg[binary]')
Uses psycopg3 async interface with connection pooling.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get(
    "GENFORGE_DATABASE_URL",
    "postgresql://genforge:genforge@localhost:5432/genforge",
)

_pool: AsyncConnectionPool | None = None


# ---------------------------------------------------------------------------
# Pool lifecycle
# ---------------------------------------------------------------------------

async def init_pool() -> None:
    """Create the async connection pool and ensure tables exist."""
    global _pool
    _pool = AsyncConnectionPool(
        conninfo=DATABASE_URL,
        min_size=2,
        max_size=10,
        kwargs={"row_factory": dict_row, "autocommit": False},
    )
    await _pool.open()
    await _create_tables()


async def close_pool() -> None:
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())[:8]


# ---------------------------------------------------------------------------
# DDL — create tables if they don't exist
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS schemas (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    schema_def  JSONB NOT NULL,
    category    TEXT NOT NULL DEFAULT 'custom',
    tags        JSONB NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS connections (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    connector_type  TEXT NOT NULL,
    host            TEXT NOT NULL,
    port            INTEGER,
    auth_method     TEXT NOT NULL DEFAULT 'basic',
    credentials     JSONB NOT NULL DEFAULT '{}',
    options         JSONB NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'untested',
    last_health_check TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,
    schema_id       TEXT NOT NULL REFERENCES schemas(id) ON DELETE CASCADE,
    connection_id   TEXT REFERENCES connections(id) ON DELETE SET NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    count           INTEGER NOT NULL DEFAULT 100,
    batch_size      INTEGER NOT NULL DEFAULT 500,
    records_sent    INTEGER NOT NULL DEFAULT 0,
    records_failed  INTEGER NOT NULL DEFAULT 0,
    progress_pct    REAL NOT NULL DEFAULT 0,
    errors          JSONB NOT NULL DEFAULT '[]',
    options         JSONB NOT NULL DEFAULT '{}',
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    duration_seconds REAL
);

CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    username    TEXT UNIQUE NOT NULL,
    password    TEXT NOT NULL,
    email       TEXT UNIQUE,
    role        TEXT NOT NULL DEFAULT 'user',
    display_name TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_schemas_category ON schemas(category);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_started ON jobs(started_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Migration: add email column if it doesn't exist (safe for existing installs)
DO $$ BEGIN
  ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT UNIQUE;
EXCEPTION WHEN others THEN NULL;
END $$;
"""


async def _create_tables() -> None:
    async with _pool.connection() as conn:
        await conn.execute(_DDL)
        await conn.commit()


# ---------------------------------------------------------------------------
# Schemas CRUD
# ---------------------------------------------------------------------------

async def create_schema(
    name: str,
    description: str,
    schema_def: dict,
    category: str = "custom",
    tags: list[str] | None = None,
) -> dict:
    sid = _new_id()
    now = _now()
    async with _pool.connection() as conn:
        await conn.execute(
            """INSERT INTO schemas (id, name, description, schema_def, category, tags, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (sid, name, description, json.dumps(schema_def), category, json.dumps(tags or []), now, now),
        )
        await conn.commit()
    return {
        "id": sid, "name": name, "description": description,
        "schema": schema_def, "category": category, "tags": tags or [],
        "created_at": now, "updated_at": now,
    }


async def get_schema(schema_id: str) -> dict | None:
    async with _pool.connection() as conn:
        row = await conn.execute(
            "SELECT * FROM schemas WHERE id = %s", (schema_id,)
        )
        r = await row.fetchone()
    if not r:
        return None
    return _row_to_schema(r)


async def list_schemas() -> list[dict]:
    async with _pool.connection() as conn:
        cur = await conn.execute("SELECT * FROM schemas ORDER BY name")
        rows = await cur.fetchall()
    return [_row_to_schema(r) for r in rows]


async def delete_schema(schema_id: str) -> bool:
    async with _pool.connection() as conn:
        cur = await conn.execute("DELETE FROM schemas WHERE id = %s", (schema_id,))
        await conn.commit()
        return cur.rowcount > 0


def _row_to_schema(r: dict) -> dict:
    return {
        "id": r["id"],
        "name": r["name"],
        "description": r["description"],
        "schema": r["schema_def"] if isinstance(r["schema_def"], dict) else json.loads(r["schema_def"]),
        "category": r["category"],
        "tags": r["tags"] if isinstance(r["tags"], list) else json.loads(r["tags"]),
        "created_at": _ts(r["created_at"]),
        "updated_at": _ts(r["updated_at"]),
    }


# ---------------------------------------------------------------------------
# Connections CRUD
# ---------------------------------------------------------------------------

async def create_connection(
    name: str,
    connector_type: str,
    host: str,
    port: int | None,
    auth_method: str,
    credentials: dict | None = None,
    options: dict | None = None,
) -> dict:
    cid = _new_id()
    now = _now()
    async with _pool.connection() as conn:
        await conn.execute(
            """INSERT INTO connections
               (id, name, connector_type, host, port, auth_method, credentials, options, status, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'untested', %s)""",
            (cid, name, connector_type, host, port, auth_method,
             json.dumps(credentials or {}), json.dumps(options or {}), now),
        )
        await conn.commit()
    return _conn_dict(cid, name, connector_type, host, port, auth_method,
                      credentials or {}, options or {}, "untested", None, now)


async def get_connection(conn_id: str) -> dict | None:
    async with _pool.connection() as conn:
        cur = await conn.execute("SELECT * FROM connections WHERE id = %s", (conn_id,))
        r = await cur.fetchone()
    return _row_to_conn(r) if r else None


async def get_connection_with_creds(conn_id: str) -> dict | None:
    """Like get_connection but includes credentials (for server-side push)."""
    async with _pool.connection() as conn:
        cur = await conn.execute("SELECT * FROM connections WHERE id = %s", (conn_id,))
        r = await cur.fetchone()
    if not r:
        return None
    d = _row_to_conn(r)
    d["credentials"] = r["credentials"] if isinstance(r["credentials"], dict) else json.loads(r["credentials"])
    return d


async def list_connections() -> list[dict]:
    async with _pool.connection() as conn:
        cur = await conn.execute("SELECT * FROM connections ORDER BY name")
        rows = await cur.fetchall()
    return [_row_to_conn(r) for r in rows]


async def update_connection_status(conn_id: str, status: str) -> None:
    now = _now()
    async with _pool.connection() as conn:
        await conn.execute(
            "UPDATE connections SET status = %s, last_health_check = %s WHERE id = %s",
            (status, now, conn_id),
        )
        await conn.commit()


async def delete_connection(conn_id: str) -> bool:
    async with _pool.connection() as conn:
        cur = await conn.execute("DELETE FROM connections WHERE id = %s", (conn_id,))
        await conn.commit()
        return cur.rowcount > 0


def _conn_dict(cid, name, connector_type, host, port, auth_method,
               credentials, options, status, last_hc, created_at) -> dict:
    return {
        "id": cid, "name": name, "connector_type": connector_type,
        "host": host, "port": port, "auth_method": auth_method,
        "options": options,
        "status": status, "last_health_check": _ts(last_hc) if last_hc else None,
        "created_at": _ts(created_at) if not isinstance(created_at, str) else created_at,
    }


def _row_to_conn(r: dict) -> dict:
    return {
        "id": r["id"], "name": r["name"], "connector_type": r["connector_type"],
        "host": r["host"], "port": r["port"], "auth_method": r["auth_method"],
        "options": r["options"] if isinstance(r["options"], dict) else json.loads(r["options"]),
        "status": r["status"],
        "last_health_check": _ts(r["last_health_check"]) if r.get("last_health_check") else None,
        "created_at": _ts(r["created_at"]),
    }


# ---------------------------------------------------------------------------
# Jobs CRUD
# ---------------------------------------------------------------------------

async def create_job(
    schema_id: str,
    connection_id: str,
    count: int = 100,
    batch_size: int = 500,
    options: dict | None = None,
) -> dict:
    jid = _new_id()
    async with _pool.connection() as conn:
        await conn.execute(
            """INSERT INTO jobs (id, schema_id, connection_id, status, count, batch_size, options)
               VALUES (%s, %s, %s, 'pending', %s, %s, %s)""",
            (jid, schema_id, connection_id, count, batch_size, json.dumps(options or {})),
        )
        await conn.commit()
    return {
        "id": jid, "schema_id": schema_id, "connection_id": connection_id,
        "status": "pending", "count": count, "batch_size": batch_size,
        "records_sent": 0, "records_failed": 0, "progress_pct": 0,
        "errors": [], "options": options or {},
        "started_at": None, "completed_at": None, "duration_seconds": None,
    }


async def update_job(job_id: str, **fields) -> None:
    if not fields:
        return
    # Serialize JSON fields
    for k in ("errors", "options"):
        if k in fields and isinstance(fields[k], (list, dict)):
            fields[k] = json.dumps(fields[k])
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [job_id]
    async with _pool.connection() as conn:
        await conn.execute(
            f"UPDATE jobs SET {set_clause} WHERE id = %s", values
        )
        await conn.commit()


async def get_job(job_id: str) -> dict | None:
    async with _pool.connection() as conn:
        cur = await conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
        r = await cur.fetchone()
    return _row_to_job(r) if r else None


async def list_jobs() -> list[dict]:
    async with _pool.connection() as conn:
        cur = await conn.execute("SELECT * FROM jobs ORDER BY started_at DESC NULLS LAST")
        rows = await cur.fetchall()
    return [_row_to_job(r) for r in rows]


def _row_to_job(r: dict) -> dict:
    return {
        "id": r["id"],
        "schema_id": r["schema_id"],
        "connection_id": r["connection_id"],
        "status": r["status"],
        "count": r["count"],
        "batch_size": r["batch_size"],
        "records_sent": r["records_sent"],
        "records_failed": r["records_failed"],
        "progress_pct": r["progress_pct"],
        "errors": r["errors"] if isinstance(r["errors"], list) else json.loads(r["errors"]),
        "options": r["options"] if isinstance(r["options"], dict) else json.loads(r["options"]),
        "started_at": _ts(r["started_at"]) if r.get("started_at") else None,
        "completed_at": _ts(r["completed_at"]) if r.get("completed_at") else None,
        "duration_seconds": r["duration_seconds"],
    }


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

async def get_stats() -> dict:
    async with _pool.connection() as conn:
        sc = await (await conn.execute("SELECT count(*) as c FROM schemas")).fetchone()
        cc = await (await conn.execute("SELECT count(*) as c FROM connections")).fetchone()
        jc = await (await conn.execute("SELECT count(*) as c FROM jobs")).fetchone()
        rc = await (await conn.execute(
            "SELECT coalesce(sum(records_sent),0) as c FROM jobs"
        )).fetchone()
        ac = await (await conn.execute(
            "SELECT count(*) as c FROM jobs WHERE status IN ('pending','running')"
        )).fetchone()
        comp = await (await conn.execute(
            "SELECT count(*) as c FROM jobs WHERE status = 'completed'"
        )).fetchone()
        fail = await (await conn.execute(
            "SELECT count(*) as c FROM jobs WHERE status = 'failed'"
        )).fetchone()
    return {
        "total_schemas": sc["c"],
        "total_connections": cc["c"],
        "total_jobs": jc["c"],
        "records_generated": rc["c"],
        "active_jobs": ac["c"],
        "completed_jobs": comp["c"],
        "failed_jobs": fail["c"],
    }


# ---------------------------------------------------------------------------
# Users CRUD
# ---------------------------------------------------------------------------

async def create_user(
    username: str,
    password: str,
    role: str = "user",
    display_name: str = "",
    email: str = "",
) -> dict:
    import hashlib
    uid = _new_id()
    now = _now()
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    async with _pool.connection() as conn:
        await conn.execute(
            """INSERT INTO users (id, username, password, email, role, display_name, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (username) DO NOTHING""",
            (uid, username, pw_hash, email or None, role, display_name or username, now),
        )
        await conn.commit()
    return {"id": uid, "username": username, "role": role,
            "display_name": display_name or username, "email": email, "created_at": now}


async def authenticate_user(username: str, password: str) -> dict | None:
    import hashlib
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    async with _pool.connection() as conn:
        cur = await conn.execute(
            "SELECT * FROM users WHERE username = %s AND password = %s",
            (username, pw_hash),
        )
        r = await cur.fetchone()
    if not r:
        return None
    return {
        "id": r["id"], "username": r["username"], "role": r["role"],
        "display_name": r["display_name"], "created_at": _ts(r["created_at"]),
    }


async def list_users() -> list[dict]:
    async with _pool.connection() as conn:
        cur = await conn.execute("SELECT id, username, role, display_name, created_at FROM users ORDER BY username")
        rows = await cur.fetchall()
    return [{"id": r["id"], "username": r["username"], "role": r["role"],
             "display_name": r["display_name"], "created_at": _ts(r["created_at"])} for r in rows]


async def delete_user(user_id: str) -> bool:
    async with _pool.connection() as conn:
        cur = await conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
        await conn.commit()
        return cur.rowcount > 0


async def get_user_by_username(username: str) -> dict | None:
    """Look up a user by username (without password check)."""
    async with _pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id, username, email, role, display_name, created_at FROM users WHERE username = %s",
            (username,),
        )
        r = await cur.fetchone()
    if not r:
        return None
    return {
        "id": r["id"], "username": r["username"], "email": r.get("email", ""),
        "role": r["role"], "display_name": r["display_name"],
        "created_at": _ts(r["created_at"]),
    }


async def get_user_by_email(email: str) -> dict | None:
    """Look up a user by email address."""
    async with _pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id, username, email, role, display_name, created_at FROM users WHERE email = %s",
            (email,),
        )
        r = await cur.fetchone()
    if not r:
        return None
    return {
        "id": r["id"], "username": r["username"], "email": r.get("email", ""),
        "role": r["role"], "display_name": r["display_name"],
        "created_at": _ts(r["created_at"]),
    }


async def update_user_password(user_id: str, new_password: str) -> bool:
    """Update a user's password."""
    import hashlib
    pw_hash = hashlib.sha256(new_password.encode()).hexdigest()
    async with _pool.connection() as conn:
        cur = await conn.execute(
            "UPDATE users SET password = %s WHERE id = %s",
            (pw_hash, user_id),
        )
        await conn.commit()
        return cur.rowcount > 0


async def check_username_exists(username: str) -> bool:
    """Check if a username is already taken."""
    async with _pool.connection() as conn:
        cur = await conn.execute(
            "SELECT 1 FROM users WHERE username = %s", (username,)
        )
        return await cur.fetchone() is not None


async def check_email_exists(email: str) -> bool:
    """Check if an email is already registered."""
    if not email:
        return False
    async with _pool.connection() as conn:
        cur = await conn.execute(
            "SELECT 1 FROM users WHERE email = %s", (email,)
        )
        return await cur.fetchone() is not None


async def seed_default_users() -> None:
    """Create default admin and user accounts if they don't exist."""
    await create_user("admin", "admin123", role="admin", display_name="Administrator",
                      email="admin@genforge.local")
    await create_user("user", "user123", role="user", display_name="Regular User",
                      email="user@genforge.local")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(val: Any) -> str | None:
    """Convert a datetime or string to ISO string."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)
