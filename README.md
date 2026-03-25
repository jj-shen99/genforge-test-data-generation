# GenForge — Test Data Generation Framework

A unified, self-service platform for generating realistic, schema-driven synthetic data
and pushing it directly into external systems through authenticated connectors.
All metadata (schemas, connections, jobs, users) is persisted in **PostgreSQL**.

**54 built-in schema templates** across **13 categories** · **16 push connectors** · **User authentication** · **PostgreSQL persistence** · **Light / Dark theme** · **Real-time API health** · **Edge-case data generation**

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt
pip install -e .

# 2. Start PostgreSQL (macOS Homebrew)
brew services start postgresql@16
# Create database & user (first time only)
createuser -s genforge
createdb genforge -O genforge
psql -U genforge -d postgres -c "ALTER USER genforge WITH PASSWORD 'genforge';"

# 3. Start the API server (port 3800)
export GENFORGE_DATABASE_URL=postgresql://genforge:genforge@localhost:5432/genforge
uvicorn datagen.api.server:app --reload --port 3800

# 4. Open the dashboard (port 3880)
python -m http.server 3880 -d dashboard

# 5. Log in with default credentials
#    admin / admin123  — Full access (admin)
#    user  / user123   — Read-only access (regular)

# 6. Generate data from CLI
genforge generate --schema configs/schemas/servicenow_incident.json --count 100 --output out.json
genforge push --schema configs/schemas/servicenow_incident.json --target configs/connections/servicenow_dev.json --count 50
```

## Project Structure

```
test-data-generation-ai/
├── datagen/                       # Core Python package
│   ├── engine/                    # Schema engine & generators
│   │   ├── schema_parser.py       # JSON Schema parser with x-datagen extensions
│   │   ├── generators.py          # Data generation primitives (Faker + custom)
│   │   ├── timeseries.py          # Time-series pattern engine
│   │   └── pipeline.py            # Multi-schema generation pipeline
│   ├── connectors/                # Connector SDK & 16 implementations
│   │   ├── base.py                # Abstract connector interface
│   │   ├── registry.py            # Plugin discovery & registration
│   │   ├── aws_dynamodb.py        # AWS DynamoDB
│   │   ├── aws_kinesis.py         # AWS Kinesis Data Streams
│   │   ├── aws_s3.py              # AWS S3
│   │   ├── aws_sqs.py             # AWS SQS
│   │   ├── clickhouse.py          # ClickHouse (HTTP interface)
│   │   ├── cribl.py               # Cribl Stream (HEC)
│   │   ├── elasticsearch.py       # Elasticsearch / OpenSearch (Bulk API)
│   │   ├── grafana_loki.py        # Grafana Loki (Push API)
│   │   ├── kafka.py               # Apache Kafka (confluent-kafka)
│   │   ├── mongodb.py             # MongoDB (insert_many)
│   │   ├── postgres.py            # PostgreSQL (SQL)
│   │   ├── prometheus.py          # Prometheus (Remote Write)
│   │   ├── redis_connector.py     # Redis (hash/string/list)
│   │   ├── servicenow.py          # ServiceNow (Table/Import Set/Event API)
│   │   ├── trino.py               # Trino (DBAPI)
│   │   └── victoriametrics.py     # VictoriaMetrics (import/write API)
│   ├── db/                        # PostgreSQL persistence layer
│   │   ├── __init__.py
│   │   └── database.py            # Async CRUD with psycopg3 + connection pool
│   ├── api/
│   │   └── server.py              # FastAPI backend (port 3800)
│   ├── models/
│   │   └── models.py              # Pydantic request/response models
│   └── cli.py                     # CLI entry point
├── dashboard/
│   └── index.html                 # Web dashboard SPA (port 3880, light/dark theme)
├── configs/
│   ├── schemas/                   # Example JSON schemas
│   └── connections/               # Example connection configs
├── deploy/
│   ├── Dockerfile                 # Container image
│   └── docker-compose.yml         # Full stack (API + dashboard + Postgres + Redis)
├── docs/
│   ├── architecture.md            # Architecture & component details
│   ├── user-guide.md              # End-user guide & CLI reference
│   └── TEST_DATA_GENERATION.md    # Feature specification
├── tests/
│   └── test_engine.py             # Engine & pipeline tests
├── .env.example                   # Database connection string config
├── requirements.txt
├── setup.py
└── README.md
```

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Web Dashboard (SPA)                        │
│       Schema Studio · Connections · Generate & Push          │
│   Connector Catalog · User Management · Light/Dark Theme     │
│   Login · Role-Based Access · API Health · Edge-Case Toggle  │
│                    http://localhost:3880                      │
└────────────────────────┬─────────────────────────────────────┘
                         │ REST + WebSocket
┌────────────────────────▼─────────────────────────────────────┐
│                    API Server (FastAPI)                        │
│               http://localhost:3800                            │
│  /api/health · /api/schemas · /api/generate · /api/jobs      │
│  /api/auth/login · /api/auth/users · /api/connections/test   │
└────────────────────────┬─────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌─────────────────┐ ┌──────────────┐ ┌───────────────┐
│  Schema Engine   │ │  Connector   │ │  PostgreSQL   │
│  SchemaParser    │ │  Layer       │ │  Database     │
│  generators.py   │ │  16 targets  │ │  schemas      │
│  timeseries.py   │ │  Auth/Batch  │ │  connections  │
│  pipeline.py     │ │  Retry       │ │  jobs · users │
└─────────────────┘ └──────────────┘ └───────────────┘
```

## Supported Push Targets (16 connectors)

| Category       | Connectors                                              |
|----------------|---------------------------------------------------------|
| Cloud          | AWS DynamoDB, AWS Kinesis, AWS S3, AWS SQS              |
| Database       | ClickHouse, MongoDB, PostgreSQL, Redis                  |
| Big Data       | Apache Kafka, Trino                                     |
| ITSM           | ServiceNow (Table API, Import Set, Events)              |
| Observability  | Cribl Stream, Elasticsearch, Grafana Loki, Prometheus, VictoriaMetrics |

## Schema Templates (54 templates, alphabetically sorted)

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

## User Authentication

GenForge includes role-based authentication:

| Role    | Permissions |
|---------|-------------|
| **admin** | Full access: create/edit/delete schemas and connections, push data, manage users |
| **user**  | Read access: view schemas and connections, generate previews, view connector catalog |

**Default accounts** (seeded on first startup):

| Username | Password   | Role  |
|----------|------------|-------|
| `admin`  | `admin123` | admin |
| `user`   | `user123`  | user  |

## Ports

| Service    | Port |
|------------|------|
| API Server | 3800 |
| Dashboard  | 3880 |
| PostgreSQL | 5432 |

## Database

GenForge uses **PostgreSQL** for persistent metadata storage:

- **schemas** — template definitions, categories, tags
- **connections** — connector configs with encrypted credentials (JSONB)
- **jobs** — push job history, record counts, errors, durations
- **users** — user accounts with hashed passwords and roles

Configure via environment variable:
```bash
export GENFORGE_DATABASE_URL=postgresql://genforge:genforge@localhost:5432/genforge
```

Tables are auto-created on first startup. See `.env.example` for reference.

## Dashboard Features

- **54 built-in schema templates** across 13 categories, alphabetically sorted
- **16 push connectors** — ServiceNow, Elasticsearch, Kafka, MongoDB, PostgreSQL, Prometheus, VictoriaMetrics, Cribl, Grafana Loki, ClickHouse, Redis, Trino, AWS DynamoDB, AWS S3, AWS SQS, AWS Kinesis
- **User authentication** — login page, admin/user roles, session persistence, role-based UI
- **User management** — admin panel for creating and deleting users
- **PostgreSQL persistence** — schemas, connections, jobs, and users survive server restarts
- **Light / Dark theme** — toggle in sidebar footer, persisted to localStorage
- **Load schema from file** — import JSON Schema files (raw or wrapped format) via file picker
- **Schema category filters** — filter by all 13 categories with color-coded tags
- **Connection testing** — real backend API health check via connector `validate_connection()`
- **Edge-case toggle** — inject boundary values (empty strings, minimums, nulls) for testing
- **Copy & Download** — preview JSON with one-click copy or download

## Documentation

- **[Architecture](docs/architecture.md)** — system diagram, components, data flow, configuration
- **[User Guide](docs/user-guide.md)** — installation, dashboard guide, CLI reference, schema spec, push target config
- **[Feature Specification](docs/TEST_DATA_GENERATION.md)** — full feature spec with template library and API reference

## Docker Deployment

```bash
cd deploy
docker-compose up -d
```

## License

MIT
