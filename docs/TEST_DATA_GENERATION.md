# Test Data Generation

## Overview

**GenForge** is a full-stack test data generation framework that enables users to generate realistic, schema-driven synthetic data and push it directly to external systems. It features a FastAPI backend with PostgreSQL persistence, a web dashboard SPA with user authentication, 54 built-in schema templates across 13 categories, and 16 push connectors.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Feature Summary](#feature-summary)
3. [Database](#database)
4. [Schema Specification](#schema-specification)
5. [Template Library](#template-library)
6. [Push to Instance](#push-to-instance)
7. [User Authentication](#user-authentication)
8. [User Guide](#user-guide)
9. [API Reference](#api-reference)
10. [Backend Dependencies](#backend-dependencies)

---

## Architecture

### High-Level Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   Web Dashboard (Single-Page App)                       │
│                                                                         │
│  ┌────────────────┐  ┌──────────────────┐  ┌────────────────────────┐  │
│  │ Template Picker │  │ Schema Editor    │  │ Generated Data Viewer  │  │
│  │ (13 categories, │  │ (JSON textarea,  │  │ (JSON preview, copy,   │  │
│  │  54 templates)  │  │  file upload)    │  │  download, stats)      │  │
│  └────────┬───────┘  └────────┬─────────┘  └────────────┬───────────┘  │
│           │                   │                          │              │
│           ▼                   ▼                          ▼              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                   Push to Instance Panel                        │   │
│  │  Connections → Backend API → 16 connectors (ServiceNow,         │   │
│  │  Elasticsearch, Kafka, MongoDB, ClickHouse, Redis, Cribl,       │   │
│  │  Grafana Loki, Prometheus, VictoriaMetrics, Trino, AWS …)       │   │
│  └──────────────────────────┬──────────────────────────────────────┘   │
│                 http://localhost:3880                                    │
└──────────────────────────────┼──────────────────────────────────────────┘
                               │  REST + WebSocket
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    API Server (FastAPI + Python)                          │
│                    http://localhost:3800                                  │
│                                                                          │
│  ┌──────────────────────┐   ┌──────────────────────────────────────┐    │
│  │ Schema Engine         │   │ Connector Layer (16 connectors)      │    │
│  │  SchemaParser         │   │  Cloud: DynamoDB, Kinesis, S3, SQS   │    │
│  │  generators.py        │   │  DB: ClickHouse, Mongo, PG, Redis    │    │
│  │  timeseries.py        │   │  BigData: Kafka, Trino               │    │
│  │  pipeline.py          │   │  Obs: Cribl, ES, Loki, Prom, VM     │    │
│  └──────────────────────┘   │  ITSM: ServiceNow                    │    │
│                              └──────────────────────────────────────┘    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ PostgreSQL Database (psycopg3 async + connection pool)           │   │
│  │  schemas · connections · jobs · users                            │   │
│  │  postgresql://genforge:genforge@localhost:5432/genforge          │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     External Systems (16 targets)                        │
│  Cloud: AWS DynamoDB · AWS Kinesis · AWS S3 · AWS SQS                   │
│  Database: ClickHouse · MongoDB · PostgreSQL · Redis                     │
│  Big Data: Apache Kafka · Trino                                          │
│  ITSM: ServiceNow                                                        │
│  Observability: Cribl · Elasticsearch · Grafana Loki · Prometheus · VM  │
└──────────────────────────────────────────────────────────────────────────┘
```

### Frontend Stack

| Component | Technology |
|---|---|
| Dashboard | Single-page HTML/CSS/JS (no build step) |
| State management | JavaScript `state` object |
| HTTP client | `fetch` API (base URL `http://localhost:3800/api`) |
| Styling | CSS custom properties with Light/Dark theme |

### Backend Stack

| Component | Technology |
|---|---|
| API server | FastAPI (Python, async) |
| Database | PostgreSQL 16 via psycopg3 + AsyncConnectionPool |
| Data generation | SchemaParser with Faker + custom generators |
| Push connectors | httpx (ServiceNow), native client libraries per target |
| Models | Pydantic v2 |

### Request Flow

1. **Generate**: User selects a schema template → frontend calls `POST /api/generate` → backend generates `N` records → response displayed in the UI.
2. **Push**: User selects a connection + schema → frontend registers both on backend → creates a job via `POST /api/jobs` → backend generates records, pushes via connector, persists job result in PostgreSQL.

---

## Feature Summary

### Core Capabilities

- **Schema-driven generation** — JSON Schema dialect supporting `string`, `integer`, `number`, `boolean`, `array`, `enum`, `format` (uuid, email, ipv4, date-time), and `x-datagen-weight` for weighted enum distribution.
- **Edge case injection** — Toggle to generate boundary values, empty strings, and extreme numbers.
- **Configurable volume** — Generate 1 to 10,000 records per batch.
- **54 built-in templates** — Pre-configured schemas across 13 categories covering datacenter, cloud, ITSM, observability, databases, CI/CD, security, networking, and more.
- **File upload** — Import schemas from `.json` files via file picker.
- **Copy & download** — One-click copy to clipboard or download as JSON file.
- **Push to 16 external systems** — Direct data ingestion via authenticated connectors, all routed through the backend API (no CORS issues).
- **PostgreSQL persistence** — Schemas, connections, jobs, and users persist across server restarts.
- **User authentication** — Login page with admin and regular user roles; role-based UI controls.
- **Real-time WebSocket updates** — Job progress broadcast to connected dashboard clients.

---

## Database

GenForge uses **PostgreSQL** for persistent metadata storage. The database module (`datagen/db/database.py`) provides:

- **Async connection pooling** via `psycopg3` + `AsyncConnectionPool`
- **Auto-migration** — tables are created automatically on first startup
- **JSONB storage** — schema definitions, connection credentials, job errors stored as JSONB

### Tables

| Table | Purpose | Key Fields |
|---|---|---|
| `schemas` | Template definitions | id, name, schema_def (JSONB), category, tags |
| `connections` | Connector configurations | id, name, connector_type, host, credentials (JSONB) |
| `jobs` | Push job history | id, schema_id, connection_id, status, records_sent, errors |
| `users` | User accounts | id, username, password (SHA-256), role, display_name |

### Configuration

```bash
export GENFORGE_DATABASE_URL=postgresql://genforge:genforge@localhost:5432/genforge
```

See `.env.example` for reference.

---

## Schema Specification

Schemas follow JSON Schema format with GenForge extensions.

### Supported Types & Constraints

| Type | Description | Constraints |
|---|---|---|
| `string` | Text values | `enum`, `format` (uuid, email, ipv4, date-time, date), `pattern` |
| `integer` | Whole numbers | `minimum`, `maximum`, `enum` |
| `number` | Floating-point numbers | `minimum`, `maximum`, `enum` |
| `boolean` | `true` / `false` | — |
| `object` | Nested object | `properties` |

### GenForge Extensions

| Extension | Description |
|---|---|
| `x-datagen-weight` | Array of weights for `enum` values (controls distribution) |
| `x-datagen-faker` | Faker method to use (e.g., `internet.domain`, `name.full_name`) |
| `x-datagen-category` | Schema category for template organization |
| `x-datagen-tags` | Array of tags for filtering |

### Example Schema

```json
{
  "type": "object",
  "properties": {
    "username": {"type": "string"},
    "email": {"type": "string", "format": "email"},
    "age": {"type": "integer", "minimum": 18, "maximum": 80},
    "role": {"type": "string", "enum": ["admin", "user", "editor"], "x-datagen-weight": [5, 80, 15]},
    "salary": {"type": "number", "minimum": 30000.00, "maximum": 200000.00},
    "is_active": {"type": "boolean"}
  }
}
```

---

## Template Library

The dashboard ships with **54 pre-built templates** organized into **13 categories**.

### Complete Template List (alphabetically sorted)

| # | Schema Name | Category |
|---|-------------|----------|
| 1 | A/B Test Result | analytics |
| 2 | ArgoCD Sync Event | cicd |
| 3 | AWS CloudWatch Metrics | cloud |
| 4 | AWS ECS Task Event | cloud |
| 5 | AWS Lambda Invocation | cloud |
| 6 | AWS S3 Access Log | cloud |
| 7 | Azure Resource Event | cloud |
| 8 | ClickHouse Web Analytics | database |
| 9 | Cloud Cost & Billing Record | cloud |
| 10 | Cribl Syslog Events | observability |
| 11 | Data Pipeline Run | analytics |
| 12 | Disk I/O & Storage Metrics | datacenter |
| 13 | DNS Query Log | networking |
| 14 | Docker Container Event | infra |
| 15 | Elasticsearch Log Entry | observability |
| 16 | Email Gateway Log | messaging |
| 17 | Firewall Rule Log | networking |
| 18 | GCP Compute Instance Event | cloud |
| 19 | GitHub Actions Workflow Run | cicd |
| 20 | Grafana Loki Log Stream | observability |
| 21 | Incident Response Record | devops |
| 22 | IPMI Sensor Reading | datacenter |
| 23 | Jenkins Build Record | cicd |
| 24 | Kafka User Activity Events | bigdata |
| 25 | Kubernetes Pod Event | infra |
| 26 | MongoDB Aggregation Pipeline | database |
| 27 | MongoDB User Profile | database |
| 28 | Network Connections (netstat/ss) | datacenter |
| 29 | Network Flow Record | security |
| 30 | OpenTelemetry Span | observability |
| 31 | PostgreSQL Slow Query Log | database |
| 32 | Process List (ps) | datacenter |
| 33 | Product Analytics Event | analytics |
| 34 | Prometheus Alert Record | observability |
| 35 | Rack Power & Cooling | datacenter |
| 36 | Redis Cache Operation | database |
| 37 | Security Audit Event | security |
| 38 | Server CPU & Memory Metrics | datacenter |
| 39 | ServiceNow Change Request | servicenow |
| 40 | ServiceNow CMDB CI | servicenow |
| 41 | ServiceNow Incident | servicenow |
| 42 | ServiceNow Knowledge Article | servicenow |
| 43 | ServiceNow Problem | servicenow |
| 44 | ServiceNow Service Request | servicenow |
| 45 | SIEM Alert | security |
| 46 | Slack Audit Event | messaging |
| 47 | SLO Performance Report | devops |
| 48 | SNMP Trap Event | networking |
| 49 | Spark Job Metrics | bigdata |
| 50 | System Load & Uptime | datacenter |
| 51 | Terraform State Resource | infra |
| 52 | Trino Query Log | bigdata |
| 53 | VictoriaMetrics Time Series | observability |
| 54 | VMware vSphere VM Event | infra |

### Category Summary

| Category | Count |
|---|---|
| analytics | 3 |
| bigdata | 3 |
| cicd | 3 |
| cloud | 6 |
| datacenter | 7 |
| database | 5 |
| devops | 2 |
| infra | 4 |
| messaging | 2 |
| networking | 3 |
| observability | 6 |
| security | 3 |
| servicenow | 6 |

---

## Push to Instance

### Overview

The **Push to Instance** feature allows generated data to be sent directly to external systems through the backend API. All push requests are routed through the FastAPI server to avoid CORS issues.

### Workflow

1. Frontend registers a **connection** on the backend (`POST /api/connections`)
2. Frontend registers the **schema** on the backend (`POST /api/schemas`)
3. Frontend creates a **push job** (`POST /api/jobs`)
4. Backend generates records using SchemaParser, pushes via the appropriate connector
5. Job result (records sent, failed, errors) is persisted in PostgreSQL

### Supported Connectors (16)

| Connector | Protocol | Python Package |
|---|---|---|
| **AWS DynamoDB** | batch_write_item | `boto3` |
| **AWS Kinesis** | put_records | `boto3` |
| **AWS S3** | put_object | `boto3` |
| **AWS SQS** | send_message_batch | `boto3` |
| **ClickHouse** | HTTP JSONEachRow | `httpx` |
| **Cribl Stream** | HEC / REST | `httpx` |
| **Elasticsearch** | Bulk API | `httpx` |
| **Grafana Loki** | Push API | `httpx` |
| **Apache Kafka** | Kafka protocol | `confluent-kafka` |
| **MongoDB** | Wire protocol | `pymongo` |
| **PostgreSQL** | SQL | `psycopg` |
| **Prometheus** | Remote Write | `prometheus_client` |
| **Redis** | Pipeline (hash/string/list) | `redis` |
| **ServiceNow** | REST Table API | `httpx` |
| **Trino** | DBAPI INSERT | `trino` |
| **VictoriaMetrics** | Import / Write API | `httpx` |

---

## User Guide

### Quick Start

1. Start PostgreSQL: `brew services start postgresql@16`
2. Start the API server: `GENFORGE_DATABASE_URL=postgresql://genforge:genforge@localhost:5432/genforge uvicorn datagen.api.server:app --port 3800`
3. Start the dashboard: `python -m http.server 3880 -d dashboard`
4. Open `http://localhost:3880` in your browser

### Generating Data

1. Navigate to **Generate & Push** from the sidebar
2. Select a schema template from the left panel (filter by category)
3. Set the **record count** (1–10,000)
4. Click **Generate** to preview data
5. Use **Copy** or **Download** to export

### Pushing Data

1. Add a **connection** in the Connections panel (host, credentials, connector type)
2. Select a **schema** and **connection**
3. Choose the target **table** from the dropdown
4. Click **Push to Instance**
5. Monitor progress in the output panel

### Tips

- **Edge cases**: Enable for testing error handling paths
- **ServiceNow**: Use state `-5` (New) for Change Requests to avoid Business Rule errors; include `close_code` and `close_notes` for Incidents with Resolved/Closed states
- **Connections persist**: Once added, connections are saved in PostgreSQL and available across sessions

---

## User Authentication

GenForge includes role-based user authentication:

| Role | Permissions |
|---|---|
| **admin** | Full access: create/edit/delete schemas, connections, users; push data; test connections |
| **user** | Read access: view schemas, connections, connector catalog; generate previews only |

**Default accounts** (seeded on first startup):

| Username | Password | Role |
|---|---|---|
| `admin` | `admin123` | admin |
| `user` | `user123` | user |

Passwords are stored as SHA-256 hashes. Sessions are persisted to `localStorage` on the client.

---

## API Reference

### Health Check

```
GET /api/health
```

### Authentication

```
POST   /api/auth/login           # Login (returns user + token)
GET    /api/auth/users            # List all users
POST   /api/auth/users            # Create a user
DELETE /api/auth/users/{id}       # Delete a user
```

### Schemas

```
GET    /api/schemas              # List all schemas
POST   /api/schemas              # Create schema
GET    /api/schemas/{id}         # Get schema by ID
DELETE /api/schemas/{id}         # Delete schema
```

### Connections

```
GET    /api/connections          # List connections (credentials stripped)
POST   /api/connections          # Create connection
POST   /api/connections/{id}/test  # Test connection health
DELETE /api/connections/{id}     # Delete connection
```

### Jobs

```
GET    /api/jobs                 # List all jobs
POST   /api/jobs                 # Create and execute push job
GET    /api/jobs/{id}            # Get job by ID
```

### Generate (Preview)

```
POST /api/generate
Content-Type: application/json

{
  "schema": { ... },
  "count": 50,
  "output_format": "json"
}
```

### Stats

```
GET /api/stats                   # Dashboard statistics
```

### WebSocket

```
ws://localhost:3800/ws           # Real-time job progress updates
```

---

## Backend Dependencies

### Core (always required)

```bash
pip install fastapi uvicorn pydantic faker jsonschema httpx orjson
pip install "psycopg[binary]" psycopg-pool   # PostgreSQL
```

### Connector-specific (install as needed)

```bash
pip install elasticsearch       # Elasticsearch
pip install pymongo             # MongoDB
pip install confluent-kafka     # Kafka
pip install redis               # Redis
pip install trino               # Trino
pip install boto3               # AWS (DynamoDB, S3, SQS, Kinesis)
pip install prometheus_client   # Prometheus Pushgateway
```

### Install everything

```bash
pip install -e ".[all]"
```

> **Note:** Each connector gracefully handles missing packages — if a required library is not installed, the API returns a descriptive error with install instructions.

---

## File Reference

| File | Role |
|---|---|
| `datagen/api/server.py` | FastAPI backend: all REST endpoints, job execution |
| `datagen/db/database.py` | PostgreSQL persistence: async CRUD, connection pool, DDL |
| `datagen/models/models.py` | Pydantic request/response models |
| `datagen/engine/schema_parser.py` | JSON Schema parser with x-datagen extensions |
| `datagen/engine/generators.py` | Data generation primitives (Faker + custom) |
| `datagen/connectors/base.py` | Abstract connector interface |
| `datagen/connectors/registry.py` | Plugin discovery & registration (16 connectors) |
| `datagen/connectors/servicenow.py` | ServiceNow connector (Table API, Import Set, Events) |
| `datagen/connectors/elasticsearch.py` | Elasticsearch / OpenSearch connector (Bulk API) |
| `datagen/connectors/kafka.py` | Apache Kafka connector (confluent-kafka) |
| `datagen/connectors/cribl.py` | Cribl Stream connector (HEC / REST) |
| `datagen/connectors/grafana_loki.py` | Grafana Loki connector (Push API) |
| `datagen/connectors/clickhouse.py` | ClickHouse connector (HTTP JSONEachRow) |
| `datagen/connectors/redis_connector.py` | Redis connector (hash/string/list) |
| `datagen/connectors/trino.py` | Trino connector (DBAPI) |
| `datagen/connectors/victoriametrics.py` | VictoriaMetrics connector (Import/Write API) |
| `dashboard/index.html` | Web dashboard SPA (54 templates, light/dark theme) |
| `.env.example` | Database connection string configuration |
