# Test Data Generation

## Overview

**GenForge** is a full-stack test data generation framework that enables users to generate realistic, schema-driven synthetic data and push it directly to external systems. It features a FastAPI backend with PostgreSQL persistence, a web dashboard SPA, and 54 built-in schema templates across 13 categories.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Feature Summary](#feature-summary)
3. [Database](#database)
4. [Schema Specification](#schema-specification)
5. [Template Library](#template-library)
6. [Push to Instance](#push-to-instance)
7. [User Guide](#user-guide)
8. [API Reference](#api-reference)
9. [Backend Dependencies](#backend-dependencies)

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
│  │  Connections → Backend API → ServiceNow, Elasticsearch,         │   │
│  │  Kafka, MongoDB, PostgreSQL, Prometheus, AWS S3, AWS DynamoDB   │   │
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
│  │ Schema Engine         │   │ Connector Layer                      │    │
│  │  SchemaParser         │   │  ServiceNow · Elasticsearch · Kafka  │    │
│  │  generators.py        │   │  MongoDB · PostgreSQL · Prometheus   │    │
│  │  timeseries.py        │   │  AWS S3 · AWS DynamoDB              │    │
│  │  pipeline.py          │   │  Auth · Batch · Retry               │    │
│  └──────────────────────┘   └──────────────────────────────────────┘    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ PostgreSQL Database (psycopg3 async + connection pool)           │   │
│  │  schemas · connections · jobs                                    │   │
│  │  postgresql://genforge:genforge@localhost:5432/genforge          │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     External Systems                                     │
│  ServiceNow · Elasticsearch · Kafka · MongoDB · Prometheus              │
│  AWS DynamoDB · AWS S3 · PostgreSQL                                     │
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
- **Push to 8 external systems** — Direct data ingestion via authenticated connectors, all routed through the backend API (no CORS issues).
- **PostgreSQL persistence** — Schemas, connections, and jobs persist across server restarts.
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

### Category Index

| Category | Count | Templates |
|---|---|---|
| **servicenow** | 6 | Incident, Change Request, CMDB CI, Problem, Service Request, Knowledge Article |
| **observability** | 5 | VictoriaMetrics Time Series, Elasticsearch Log Entry, Cribl Syslog, Grafana Loki Log Stream, OpenTelemetry Span, Prometheus Alert Record |
| **database** | 5 | MongoDB User Profile, PostgreSQL Slow Query, ClickHouse Web Analytics, Redis Cache Operation, MongoDB Aggregation Pipeline |
| **cloud** | 6 | AWS CloudWatch Metrics, AWS S3 Access Log, AWS Lambda Invocation, AWS ECS Task Event, GCP Compute Instance, Cloud Cost & Billing |
| **bigdata** | 3 | Kafka User Activity Events, Trino Query Log, Spark Job Metrics |
| **cicd** | 3 | GitHub Actions Workflow Run, Jenkins Build Record, ArgoCD Sync Event |
| **infra** | 4 | Kubernetes Pod Event, Terraform State Resource, Docker Container Event, VMware vSphere VM Event |
| **security** | 3 | Security Audit Event, Network Flow Record, SIEM Alert |
| **datacenter** | 7 | Server CPU & Memory Metrics, Disk I/O & Storage, IPMI Sensor Reading, Rack Power & Cooling, Process List (ps), Network Connections (netstat/ss), System Load & Uptime |
| **networking** | 3 | DNS Query Log, Firewall Rule Log, SNMP Trap Event |
| **messaging** | 2 | Slack Audit Event, Email Gateway Log |
| **analytics** | 3 | Product Analytics Event, A/B Test Result, Data Pipeline Run |
| **devops** | 2 | Incident Response Record, SLO Performance Report |

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

### Supported Connectors

| Connector | Protocol | Python Package |
|---|---|---|
| **ServiceNow** | REST Table API | `httpx` |
| **Elasticsearch** | Bulk API | `elasticsearch` |
| **Apache Kafka** | Kafka protocol | `confluent-kafka` |
| **MongoDB** | Wire protocol | `pymongo` |
| **PostgreSQL** | SQL | `psycopg` |
| **Prometheus** | Pushgateway | `prometheus_client` |
| **AWS DynamoDB** | AWS SDK | `boto3` |
| **AWS S3** | AWS SDK | `boto3` |

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

## API Reference

### Health Check

```
GET /api/health
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
pip install boto3               # AWS (DynamoDB, S3)
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
| `datagen/connectors/servicenow.py` | ServiceNow connector (Table API, Import Set, Events) |
| `datagen/connectors/base.py` | Abstract connector interface |
| `datagen/connectors/registry.py` | Plugin discovery & registration |
| `dashboard/index.html` | Web dashboard SPA (54 templates, light/dark theme) |
| `.env.example` | Database connection string configuration |
