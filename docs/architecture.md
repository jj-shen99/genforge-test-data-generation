# GenForge — Architecture

## Overview

GenForge is a full-stack test data generation platform. It generates realistic, schema-driven
synthetic data and pushes it directly into external systems through authenticated connectors.

---

## System Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                    Web Dashboard (SPA)                            │
│                    http://localhost:3880                          │
│                                                                  │
│  ┌────────────────┐  ┌───────────────┐  ┌─────────────────────┐ │
│  │ Schema Studio   │  │ Connections   │  │ Generate & Push     │ │
│  │ (54 templates,  │  │ (8 targets,   │  │ (preview, batch,    │ │
│  │  load from file)│  │  auth config) │  │  edge-case toggle)  │ │
│  └───────┬────────┘  └──────┬────────┘  └──────────┬──────────┘ │
│          └──────────────────┼──────────────────────┘             │
│                             │  REST + WebSocket                  │
└─────────────────────────────┼────────────────────────────────────┘
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                    API Server (FastAPI)                           │
│                    http://localhost:3800                          │
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────────┐  │
│  │ /api/    │ │ /api/    │ │ /api/     │ │ /api/health      │  │
│  │ schemas  │ │ generate │ │ jobs      │ │ /ws (realtime)   │  │
│  └────┬─────┘ └────┬─────┘ └─────┬─────┘ └──────────────────┘  │
│       │             │             │                               │
│       ▼             ▼             ▼                               │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                     Schema Engine                            │ │
│  │  SchemaParser → generators.py → timeseries.py → pipeline.py │ │
│  └──────────────────────────┬──────────────────────────────────┘ │
│                              │                                    │
│  ┌──────────────────────────▼──────────────────────────────────┐ │
│  │                    Connector Layer                           │ │
│  │  base.py → registry.py → [servicenow, kafka, elastic, …]   │ │
│  └──────────────────────────┬──────────────────────────────────┘ │
│                              │                                    │
│  ┌──────────────────────────▼──────────────────────────────────┐ │
│  │              PostgreSQL Database (psycopg3)                  │ │
│  │  schemas · connections · jobs  (async connection pool)       │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────┼───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                      External Systems                            │
│                                                                  │
│  ITSM                          Observability                     │
│  └─ ServiceNow (Table API)     ├─ Elasticsearch (Bulk API)       │
│                                └─ Prometheus (Pushgateway)       │
│  Streaming                     Databases                         │
│  └─ Apache Kafka               ├─ PostgreSQL                     │
│                                └─ MongoDB (insert_many)          │
│  Cloud                                                           │
│  ├─ AWS DynamoDB                                                 │
│  └─ AWS S3                                                       │
└──────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. Web Dashboard

| Attribute   | Value                              |
|-------------|------------------------------------|
| Technology  | Vanilla HTML + JavaScript (SPA)    |
| Port        | 3880 (nginx in Docker, or static)  |
| API target  | `http://localhost:3800/api`         |

**Pages:**

- **Dashboard** — 8 metrics (schemas, connections, active connections, jobs, records, success rate, failed, API uptime), schema category breakdown, connections panel, connector grid, recent schemas, recent activity feed
- **Schema Studio** — browse, create, load from file, and inspect 54 built-in JSON schemas across 13 categories with field-level detail and category filter tabs
- **Connections** — configure and test target connections with auth credentials, status indicator; persisted in PostgreSQL
- **Generate & Push** — select schema + connection, set record count, edge-case toggle, preview with copy/download, or run a job
- **Job Monitor** — real-time job table with status, progress, and duration; job history persisted in PostgreSQL
- **Connector Catalog** — alphabetically sorted reference of all 8 supported push targets grouped by category
- **Theme** — Light / Dark mode toggle in sidebar footer, persisted to localStorage

### 2. API Server

| Attribute   | Value                                   |
|-------------|------------------------------------------|
| Framework   | FastAPI (Python 3.9+)                    |
| Port        | 3800                                     |
| Transport   | REST + WebSocket (`/ws`)                 |
| State       | PostgreSQL (psycopg3 async + connection pool) |

**Key endpoints:**

| Method | Path                        | Description                          |
|--------|-----------------------------|--------------------------------------|
| GET    | `/api/health`               | Health check (uptime, version)       |
| GET    | `/api/stats`                | Dashboard statistics                 |
| GET    | `/api/schemas`              | List all schemas                     |
| POST   | `/api/schemas`              | Create a new schema                  |
| POST   | `/api/generate`             | Generate records from a schema       |
| POST   | `/api/generate/timeseries`  | Generate time-series data            |
| GET    | `/api/connections`          | List connections                     |
| POST   | `/api/connections`          | Create a connection                  |
| POST   | `/api/connections/{id}/test`| Test a connection                    |
| POST   | `/api/jobs`                 | Create and run a generation job      |
| GET    | `/api/jobs`                 | List jobs                            |
| GET    | `/api/connectors`           | List available connector types       |
| WS     | `/ws`                       | Real-time job progress updates       |

### 3. Schema Engine

The engine converts JSON Schema definitions (with `x-datagen-*` extensions) into realistic records.

**Modules:**

- **`schema_parser.py`** — Resolves `$ref`, `allOf`, `oneOf`, `anyOf`; handles uniqueness, null rates, dependencies, and foreign key references
- **`generators.py`** — Type-specific generators for string, integer, number, boolean, datetime, array; Faker integration via `x-datagen-faker`; weighted choices; statistical distributions (uniform, gaussian, poisson)
- **`timeseries.py`** — Time-series patterns: sine wave, random walk, step functions, anomaly injection; structured log entry generation
- **`pipeline.py`** — Multi-schema generation with dependency resolution and cross-schema referential integrity

### 4. Connector Layer

All connectors implement `BaseConnector` (in `base.py`) which defines:

1. `authenticate()` — establish auth session
2. `validate_connection()` — test reachability
3. `push_batch(records)` — send a batch of records
4. `push_stream(records)` — send records one at a time
5. `get_target_schema()` — auto-detect target schema
6. `close()` — clean up resources

**Connector registry** (`registry.py`) provides:
- Auto-discovery of built-in connectors via module import
- Third-party plugin support via `entry_points`
- `create_connector(config)` factory function

### 5. PostgreSQL Persistence Layer

The database module (`datagen/db/database.py`) provides:

- **Async connection pooling** via `psycopg3` + `AsyncConnectionPool`
- **Auto-migration** — tables auto-created on startup
- **JSONB columns** — schema_def, credentials, options, errors
- **Tables**: `schemas`, `connections`, `jobs`

### 6. Supported Push Targets (8)

| Category       | Target           | Protocol              | Batch Size |
|----------------|------------------|-----------------------|------------|
| ITSM           | ServiceNow       | REST (Table API)      | per record |
| Observability  | Elasticsearch    | Bulk API              | all at once|
| Observability  | Prometheus       | Pushgateway           | all at once|
| Streaming      | Kafka            | Kafka protocol        | per record |
| Databases      | PostgreSQL       | SQL                   | all at once|
| Databases      | MongoDB          | insert_many           | all at once|
| Cloud Storage  | AWS DynamoDB     | batch_write_item      | 25         |
| Cloud Storage  | AWS S3           | put_object            | 1 per file |

---

## Directory Structure

```
genforge/
├── datagen/                  # Core Python package
│   ├── engine/               # Schema engine & generators
│   │   ├── schema_parser.py
│   │   ├── generators.py
│   │   ├── timeseries.py
│   │   └── pipeline.py
│   ├── connectors/           # Connector SDK & implementations
│   │   ├── base.py           # Abstract connector interface
│   │   ├── registry.py       # Plugin discovery & registration
│   │   ├── servicenow.py
│   │   ├── kafka.py
│   │   ├── elasticsearch.py
│   │   ├── mongodb.py
│   │   ├── prometheus.py
│   │   ├── aws_s3.py
│   │   ├── aws_dynamodb.py
│   │   └── ...
│   ├── db/                   # PostgreSQL persistence layer
│   │   ├── __init__.py
│   │   └── database.py       # Async CRUD, connection pool, DDL
│   ├── api/
│   │   └── server.py         # FastAPI backend (port 3800)
│   └── models/
│       └── models.py         # Pydantic request/response models
├── dashboard/
│   └── index.html            # Web dashboard SPA (port 3880)
├── configs/
│   ├── schemas/              # Example JSON schemas
│   └── connections/          # Example connection configs
├── deploy/
│   ├── Dockerfile
│   └── docker-compose.yml
├── docs/
│   ├── architecture.md       # This document
│   ├── user-guide.md         # End-user guide
│   └── TEST_DATA_GENERATION.md  # Feature specification
├── tests/
│   └── test_engine.py
├── .env.example              # Database connection string config
├── requirements.txt
├── setup.py
└── README.md
```

---

## Data Flow

### Generate (preview)

```
User → Dashboard → POST /api/generate → SchemaParser.generate(N) → JSON response → Dashboard
```

### Generate & Push (job)

```
User → Dashboard → POST /api/jobs {schema_id, connection_id, count}
  → SchemaParser.generate(count)
  → create_connector(config).authenticate()
  → push_batch(records) in batch_size chunks
  → WebSocket progress updates → Dashboard
  → Job completed/failed
```

---

## Configuration

### Environment Variables

| Variable                | Default                                                  | Description                |
|-------------------------|----------------------------------------------------------|----------------------------|
| `GENFORGE_ENV`          | `development`                                            | Runtime environment        |
| `GENFORGE_DATABASE_URL` | `postgresql://genforge:genforge@localhost:5432/genforge` | PostgreSQL connection URL  |

### Ports

| Service    | Port |
|------------|------|
| API Server | 3800 |
| Dashboard  | 3880 |
| PostgreSQL | 5432 |
| Redis      | 6379 |
