# GenForge — Test Data Generation Framework

A unified, self-service platform for generating realistic, schema-driven synthetic data
and pushing it directly into external systems through authenticated connectors.
All metadata (schemas, connections, jobs) is persisted in **PostgreSQL**.

**54 built-in schema templates** across **13 categories** · **PostgreSQL persistence** · **Light / Dark theme** · **Load schemas from file** · **Real-time API health** · **Edge-case data generation**

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

# 5. Generate data from CLI
genforge generate --schema configs/schemas/servicenow_incident.json --count 100 --output out.json
genforge push --schema configs/schemas/servicenow_incident.json --target configs/connections/servicenow_dev.json --count 50
```

## Project Structure

```
test-data-generation-ai/
├── datagen/                  # Core Python package
│   ├── engine/               # Schema engine & generators
│   │   ├── schema_parser.py  # JSON Schema parser with x-datagen extensions
│   │   ├── generators.py     # Data generation primitives (Faker + custom)
│   │   ├── timeseries.py     # Time-series pattern engine
│   │   └── pipeline.py       # Multi-schema generation pipeline
│   ├── connectors/           # Connector SDK & implementations
│   │   ├── base.py           # Abstract connector interface
│   │   ├── registry.py       # Plugin discovery & registration
│   │   ├── servicenow.py     # ServiceNow (Table/Import Set/Event API)
│   │   ├── kafka.py          # Apache Kafka producer
│   │   ├── elasticsearch.py  # Elasticsearch Bulk API
│   │   ├── mongodb.py        # MongoDB insert_many
│   │   ├── prometheus.py     # Prometheus Pushgateway
│   │   ├── aws_s3.py         # AWS S3
│   │   └── aws_dynamodb.py   # AWS DynamoDB
│   ├── db/                   # PostgreSQL persistence layer
│   │   ├── __init__.py
│   │   └── database.py       # Async CRUD with psycopg3 + connection pool
│   ├── api/
│   │   └── server.py         # FastAPI backend (port 3800)
│   ├── models/
│   │   └── models.py         # Pydantic request/response models
│   └── cli.py                # CLI entry point
├── dashboard/
│   └── index.html            # Web dashboard SPA (port 3880, light/dark theme)
├── configs/
│   ├── schemas/              # Example JSON schemas
│   └── connections/          # Example connection configs
├── deploy/
│   ├── Dockerfile            # Container image
│   └── docker-compose.yml    # Full stack (API + dashboard + Postgres + Redis)
├── docs/
│   ├── architecture.md       # Architecture & component details
│   ├── user-guide.md         # End-user guide & CLI reference
│   └── TEST_DATA_GENERATION.md  # Feature specification
├── tests/
│   └── test_engine.py        # Engine & pipeline tests
├── .env.example              # Database connection string config
├── requirements.txt
├── setup.py
└── README.md
```

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Web Dashboard (SPA)                        │
│       Schema Studio · Connections · Generate & Push          │
│   Job Monitor · Connector Catalog · Light/Dark Theme         │
│  Load Schema from File · API Health · Edge-Case Toggle       │
│                    http://localhost:3880                      │
└────────────────────────┬─────────────────────────────────────┘
                         │ REST + WebSocket
┌────────────────────────▼─────────────────────────────────────┐
│                    API Server (FastAPI)                        │
│               http://localhost:3800                            │
│    /api/health · /api/schemas · /api/generate · /api/jobs    │
└────────────────────────┬─────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌─────────────────┐ ┌──────────────┐ ┌───────────────┐
│  Schema Engine   │ │  Connector   │ │  PostgreSQL   │
│  SchemaParser    │ │  Layer       │ │  Database     │
│  generators.py   │ │  8 targets   │ │  schemas      │
│  timeseries.py   │ │  Auth/Batch  │ │  connections  │
│  pipeline.py     │ │  Retry       │ │  jobs         │
└─────────────────┘ └──────────────┘ └───────────────┘
```

## Supported Push Targets (8 connectors)

| Category             | Connectors                                     |
|----------------------|------------------------------------------------|
| ITSM                 | ServiceNow (Table API, Import Set, Events)     |
| Observability        | Prometheus Pushgateway, Elasticsearch           |
| Streaming            | Apache Kafka                                   |
| Databases            | PostgreSQL, MongoDB                            |
| Cloud                | AWS DynamoDB, AWS S3                           |

## Schema Template Categories (54 templates)

| Category        | Count | Examples                                                    |
|-----------------|-------|-------------------------------------------------------------|
| servicenow      | 6     | Incident, Change Request, CMDB CI, Problem, Service Request, Knowledge Article |
| observability   | 5     | VictoriaMetrics, Elasticsearch Logs, Loki, OpenTelemetry, Prometheus Alerts |
| database        | 5     | MongoDB User Profile, PostgreSQL Slow Query, ClickHouse Analytics, Redis Cache, MongoDB Aggregation |
| cloud           | 6     | AWS CloudWatch, AWS S3 Access, AWS Lambda, AWS ECS, GCP Compute, Cloud Cost/Billing |
| bigdata         | 3     | Kafka Events, Trino Query Log, Spark Job Metrics            |
| cicd            | 3     | GitHub Actions, Jenkins, ArgoCD                             |
| infra           | 3     | Kubernetes Pod, Terraform State, Docker Container, VMware vSphere |
| security        | 3     | Security Audit, Network Flow, SIEM Alert                    |
| datacenter      | 7     | Server CPU/Memory, Disk I/O, IPMI Sensors, Rack Power/Cooling, Process List (ps), Network Connections (netstat/ss), System Load |
| networking      | 3     | DNS Query Log, Firewall Rule Log, SNMP Trap                 |
| messaging       | 2     | Slack Audit, Email Gateway                                  |
| analytics       | 3     | Product Analytics, A/B Test, Data Pipeline Run              |
| devops          | 2     | Incident Response, SLO Performance                          |

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

Configure via environment variable:
```bash
export GENFORGE_DATABASE_URL=postgresql://genforge:genforge@localhost:5432/genforge
```

Tables are auto-created on first startup. See `.env.example` for reference.

## Dashboard Features

- **54 built-in schema templates** across 13 categories — ServiceNow, datacenter monitoring, cloud services, server processes, Kubernetes, CI/CD, security, networking, and more
- **PostgreSQL persistence** — schemas, connections, and jobs survive server restarts
- **Light / Dark theme** — toggle in sidebar footer, persisted to localStorage
- **Load schema from file** — import JSON Schema files (raw or wrapped format) via file picker
- **Schema category filters** — filter by all 13 categories with color-coded tags
- **Alphabetically sorted connector catalog** — grouped by category
- **Enhanced dashboard** — active connections, API uptime, job success rate, schema category breakdown
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
