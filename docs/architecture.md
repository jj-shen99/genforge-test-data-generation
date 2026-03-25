# GenForge — Architecture

## Overview

GenForge is a full-stack test data generation platform. It generates realistic, schema-driven
synthetic data and pushes it directly into external systems through 16 authenticated connectors.
User authentication with role-based access control protects admin operations.

### Core Capabilities

- **Schema-driven generation** — JSON Schema dialect with `x-datagen-*` extensions for weighted enums, Faker providers, distributions, null rates, uniqueness, and foreign key references
- **60 built-in templates** — pre-configured schemas across 14 categories (datacenter, cloud, ITSM, observability, databases, CI/CD, security, networking, messaging, analytics, devops)
- **Push to 16 external systems** — authenticated connectors routed through the backend API (no CORS issues)
- **Edge-case injection** — toggle to generate boundary values, empty strings, and extreme numbers
- **Configurable volume** — 1 to 10,000 records per batch
- **File upload** — import schemas from `.json` files via file picker
- **Copy & download** — one-click copy to clipboard or download as JSON file
- **PostgreSQL persistence** — schemas, connections, jobs, and users persist across restarts
- **User authentication** — login with admin/user roles; role-based UI controls
- **User registration** — self-service account creation with optional email, auto-login
- **Forgot password** — reset by username or email from the login screen
- **ML schema analysis** — portfolio quality scoring, field profiling, type distribution, recommendations
- **Real-time WebSocket updates** — job progress broadcast to connected dashboard clients

---

## System Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                    Web Dashboard (SPA)                            │
│                    http://localhost:3880                          │
│                                                                  │
│  ┌────────────────┐  ┌───────────────┐  ┌─────────────────────┐ │
│  │ Schema Studio   │  │ Connections   │  │ Generate & Push     │ │
│  │ (60 templates,  │  │ (16 targets,  │  │ (preview, batch,    │ │
│  │  load from file)│  │  auth config) │  │  edge-case toggle)  │ │
│  └───────┬────────┘  └──────┬────────┘  └──────────┬──────────┘ │
│  ┌───────┴────────┐  ┌──────┴────────┐             │            │
│  │ ML Analysis    │  │ User Mgmt     │             │            │
│  │ (quality score,│  │ (admin only)  │─────────────┘            │
│  │  field profile)│  └───────────────┘                          │
│  └────────────────┘         │  REST + WebSocket                  │
└─────────────────────────────┼────────────────────────────────────┘
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                    API Server (FastAPI)                           │
│                    http://localhost:3800                          │
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────────┐  │
│  │ /api/    │ │ /api/    │ │ /api/     │ │ /api/auth/login  │  │
│  │ schemas  │ │ generate │ │ jobs      │ │ /api/auth/register│  │
│  │          │ │          │ │           │ │ /api/auth/reset-pw│  │
│  │          │ │          │ │           │ │ /api/auth/users  │  │
│  └────┬─────┘ └────┬─────┘ └─────┬─────┘ └──────────────────┘  │
│       │             │             │                               │
│       ▼             ▼             ▼                               │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                     Schema Engine                            │ │
│  │  SchemaParser → generators.py → timeseries.py → pipeline.py │ │
│  └──────────────────────────┬──────────────────────────────────┘ │
│                              │                                    │
│  ┌──────────────────────────▼──────────────────────────────────┐ │
│  │                    Connector Layer (16 connectors)           │ │
│  │  base.py → registry.py → [servicenow, kafka, elastic, …]   │ │
│  └──────────────────────────┬──────────────────────────────────┘ │
│                              │                                    │
│  ┌──────────────────────────▼──────────────────────────────────┐ │
│  │              PostgreSQL Database (psycopg3)                  │ │
│  │  schemas · connections · jobs · users (async pool)          │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────┼───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                      External Systems                            │
│                                                                  │
│  ITSM                          Observability                     │
│  └─ ServiceNow (Table API)     ├─ Cribl Stream (HEC)            │
│                                ├─ Elasticsearch (Bulk API)       │
│  Big Data                      ├─ Grafana Loki (Push API)        │
│  ├─ Apache Kafka               ├─ Prometheus (Remote Write)      │
│  └─ Trino (DBAPI)             └─ VictoriaMetrics (Import API)   │
│                                                                  │
│  Databases                     Cloud                             │
│  ├─ ClickHouse (HTTP)          ├─ AWS DynamoDB                   │
│  ├─ MongoDB (insert_many)      ├─ AWS Kinesis                    │
│  ├─ PostgreSQL (SQL)           ├─ AWS S3                         │
│  └─ Redis (hash/string/list)   └─ AWS SQS                       │
└──────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. Web Dashboard

| Attribute        | Value                              |
|------------------|------------------------------------|
| Technology       | Vanilla HTML + JavaScript (SPA)    |
| Port             | 3880 (nginx in Docker, or static)  |
| API target       | `http://localhost:3800/api`         |
| State management | JavaScript `state` object          |
| HTTP client      | `fetch` API                        |
| Styling          | CSS custom properties (Light/Dark) |

**Pages:**

- **Dashboard** — 8 metrics (schemas, connections, active connections, jobs, records, success rate, failed, API uptime), schema category breakdown, connections panel, connector grid, recent schemas, recent activity feed
- **Schema Studio** — browse, create, load from file, and inspect 60 built-in JSON schemas (alphabetically sorted) across 14 categories with field-level detail and category filter tabs
- **Connections** — configure and test target connections with auth credentials, status indicator; persisted in PostgreSQL
- **Generate & Push** — select schema + connection, set record count, edge-case toggle, preview with copy/download, or run a job
- **Job Monitor** — real-time job table with status, progress, and duration; job history persisted in PostgreSQL
- **Connector Catalog** — alphabetically sorted reference of all 16 supported push targets grouped by category
- **User Management** — admin-only page for creating and deleting user accounts with role assignment
- **Authentication** — login overlay with session persistence (localStorage), role-based UI (admin vs regular user)
- **Theme** — Light / Dark mode toggle in sidebar footer, persisted to localStorage

### 2. API Server

| Attribute   | Value                                   |
|-------------|------------------------------------------|
| Framework   | FastAPI (Python 3.9+)                    |
| Port        | 3800                                     |
| Transport   | REST + WebSocket (`/ws`)                 |
| State       | PostgreSQL (psycopg3 async + connection pool) |
| Models      | Pydantic v2                              |

**Request flow:**

1. **Generate**: User selects a schema → `POST /api/generate` → SchemaParser generates N records → JSON response displayed in UI
2. **Push**: User selects connection + schema → backend registers both → `POST /api/jobs` → backend generates records, pushes via connector, persists result in PostgreSQL

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
| POST   | `/api/auth/login`           | Authenticate user (returns token)    |
| GET    | `/api/auth/users`           | List all users (admin)               |
| POST   | `/api/auth/users`           | Create a user (admin)                |
| DELETE | `/api/auth/users/{id}`      | Delete a user (admin)                |
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
- **Tables**: `schemas`, `connections`, `jobs`, `users`
- **Default users** — `admin`/`admin123` (admin) and `user`/`user123` (regular) seeded on startup

### 6. Supported Push Targets (16)

| Category       | Target           | Protocol              | Batch Size |
|----------------|------------------|-----------------------|------------|
| Cloud          | AWS DynamoDB     | batch_write_item      | 25         |
| Cloud          | AWS Kinesis      | put_records           | 500        |
| Cloud          | AWS S3           | put_object            | 1 per file |
| Cloud          | AWS SQS          | send_message_batch    | 10         |
| Database       | ClickHouse       | HTTP JSONEachRow      | all at once|
| Database       | MongoDB          | insert_many           | all at once|
| Database       | PostgreSQL       | SQL                   | all at once|
| Database       | Redis            | pipeline (hash/list)  | all at once|
| Big Data       | Apache Kafka     | Kafka protocol        | per record |
| Big Data       | Trino            | DBAPI INSERT          | per record |
| ITSM           | ServiceNow       | REST (Table API)      | per record |
| Observability  | Cribl Stream     | HEC / REST            | all at once|
| Observability  | Elasticsearch    | Bulk API              | all at once|
| Observability  | Grafana Loki     | Push API              | all at once|
| Observability  | Prometheus       | Remote Write          | all at once|
| Observability  | VictoriaMetrics  | Import / Write API    | all at once|

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
│   ├── connectors/           # Connector SDK & 16 implementations
│   │   ├── base.py           # Abstract connector interface
│   │   ├── registry.py       # Plugin discovery & registration
│   │   ├── aws_dynamodb.py   # AWS DynamoDB
│   │   ├── aws_kinesis.py    # AWS Kinesis
│   │   ├── aws_s3.py         # AWS S3
│   │   ├── aws_sqs.py        # AWS SQS
│   │   ├── clickhouse.py     # ClickHouse
│   │   ├── cribl.py          # Cribl Stream
│   │   ├── elasticsearch.py  # Elasticsearch / OpenSearch
│   │   ├── grafana_loki.py   # Grafana Loki
│   │   ├── kafka.py          # Apache Kafka
│   │   ├── mongodb.py        # MongoDB
│   │   ├── postgres.py       # PostgreSQL
│   │   ├── prometheus.py     # Prometheus
│   │   ├── redis_connector.py# Redis
│   │   ├── servicenow.py     # ServiceNow
│   │   ├── trino.py          # Trino
│   │   └── victoriametrics.py# VictoriaMetrics
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
│   └── user-guide.md         # End-user guide & CLI reference
├── tests/
│   ├── test_engine.py        # Engine & pipeline tests
│   ├── test_connectors.py    # Registry, base class, auth provider
│   ├── test_models.py        # Pydantic API models
│   └── test_edge_cases.py    # Boundary value & edge-case tests
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

---

## File Reference

| File | Role |
|---|---|
| `datagen/api/server.py` | FastAPI backend: all REST endpoints, job execution |
| `datagen/db/database.py` | PostgreSQL persistence: async CRUD, connection pool, DDL |
| `datagen/models/models.py` | Pydantic request/response models |
| `datagen/engine/schema_parser.py` | JSON Schema parser with x-datagen extensions |
| `datagen/engine/generators.py` | Data generation primitives (Faker + custom) |
| `datagen/engine/timeseries.py` | Time-series patterns and log entry generation |
| `datagen/engine/pipeline.py` | Multi-schema generation with dependency resolution |
| `datagen/connectors/base.py` | Abstract connector interface (`BaseConnector`) |
| `datagen/connectors/registry.py` | Plugin discovery & registration (16 connectors) |
| `datagen/connectors/auth.py` | Auth provider (session creation for connectors) |
| `datagen/cli.py` | CLI entry point (`genforge` command) |
| `dashboard/index.html` | Web dashboard SPA (60 templates, light/dark theme) |
| `setup.py` | Package definition, extras, entry points |
| `.env.example` | Database connection string configuration |
