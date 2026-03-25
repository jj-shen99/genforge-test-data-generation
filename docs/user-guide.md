# GenForge — User Guide

## Getting Started

### Prerequisites

- Python 3.9 or later
- pip
- PostgreSQL 16 (installed via Homebrew: `brew install postgresql@16`)

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd test-data-generation-ai

# Install core dependencies
pip install -r requirements.txt

# Install the package in development mode
pip install -e .

# (Optional) Install connector-specific dependencies
pip install -e ".[all]"     # All connectors
pip install -e ".[postgres]" # PostgreSQL only
pip install -e ".[kafka]"    # Kafka only
pip install -e ".[aws]"      # AWS services only
```

### Set Up PostgreSQL (first time only)

```bash
# Start PostgreSQL
brew services start postgresql@16

# Create user and database
createuser -s genforge
createdb genforge -O genforge
psql -U genforge -d postgres -c "ALTER USER genforge WITH PASSWORD 'genforge';"
```

### Start the API Server

```bash
# Set database connection
export GENFORGE_DATABASE_URL=postgresql://genforge:genforge@localhost:5432/genforge

# Option 1: Direct
python -m datagen.api.server
# → API running on http://localhost:3800

# Option 2: With uvicorn (auto-reload for development)
uvicorn datagen.api.server:app --reload --port 3800
```

> **Note:** Tables (`schemas`, `connections`, `jobs`) are auto-created on first startup. Example schemas from `configs/schemas/` are loaded automatically.

### Open the Dashboard

```bash
# Option 1: Open the file directly
open dashboard/index.html

# Option 2: Serve with Python's built-in HTTP server
python -m http.server 3880 -d dashboard
# → Dashboard at http://localhost:3880
```

### Docker Deployment

```bash
cd deploy
docker-compose up -d
# → API at http://localhost:3800
# → Dashboard at http://localhost:3880
```

---

## Dashboard Guide

### Dashboard Page

The landing page shows a comprehensive summary of your workspace:

- **Schemas** — number of loaded/created schemas (60 built-in templates)
- **Connections** — number of configured target connections (persisted in PostgreSQL)
- **Active connections** — connections with healthy status
- **Jobs run** — total generation jobs executed (persisted in PostgreSQL)
- **Records generated** — cumulative record count
- **Success rate** — percentage of completed jobs
- **Failed jobs** — count of failed generation jobs
- **API uptime** — live uptime from the `/api/health` endpoint
- **Schema categories** — visual breakdown by 14 categories (servicenow, observability, database, cloud, bigdata, cicd, infra, security, datacenter, networking, messaging, analytics, devops, generic)
- **Connections panel** — quick-view of recent connections with status
- **Available connectors** — grid of all 16 supported push targets
- **Recent schemas** — table listing schemas alphabetically with category and field count
- **Recent activity** — latest jobs with status and record counts
- **API Health** — live indicator in sidebar showing API server status (polls every 30s)
- **Theme toggle** — switch between Light and Dark mode (persisted to localStorage)
- **User badge** — shows logged-in user and role in sidebar footer; click to sign out

### Schema Studio

Browse, create, and inspect JSON schemas.

**Creating a schema:**
1. Click **+ New schema**
2. Fill in name, description, category, and tags
3. Enter a JSON schema in the editor (see [Schema Specification](#schema-specification) below)
4. Click **Create**

**Loading a schema from file:**
1. Click **Load from file** in the Schema Studio toolbar
2. Select a `.json` or `.schema` file from your filesystem
3. The file can be either:
   - A raw JSON Schema: `{"type":"object","properties":{...}}`
   - A wrapped format: `{"name":"...","category":"...","schema":{...}}`
4. The schema is automatically parsed, named, and added to your workspace

**Inspecting a schema:**
- Click any schema card to view its full JSON definition
- Field names are displayed as chips on each card
- Click **Use in generator** to jump to the Generate page
- Use **category filter tabs** to filter schemas by category

### Connections

Configure connections to external push targets.

**Adding a connection:**
1. Click **+ New connection**
2. Select the connector type (ServiceNow, Kafka, Elasticsearch, etc.)
3. Fill in host, port, auth method, and credentials
4. Add any connector-specific options as JSON (e.g., `{"table": "incident"}`)
5. Click **Create**

**Testing a connection:**
- Click **Test** on any connection card to verify connectivity
- A green dot indicates a healthy connection; red indicates an error

### Generate & Push

Generate test data and optionally push it to a target.

1. Select a **schema** from the dropdown
2. (Optional) Select a **target connection**
3. Set the **record count** (1–100,000) and **batch size**
4. Click **Preview 5 records** to see a sample
5. Click **Generate** to create a job
6. Results appear below — record count, duration, and push status

### Job Monitor

View all generation jobs with real-time status.

| Column   | Description                          |
|----------|--------------------------------------|
| ID       | Unique job identifier                |
| Schema   | The schema used for generation       |
| Status   | pending / running / completed / failed |
| Records  | Sent count and failure count         |
| Duration | Total execution time                 |
| Time     | Job start time                       |

### Connector Catalog

Reference page listing all 16 supported connectors, alphabetically sorted and grouped by category, with type identifiers and supported auth methods.

### User Management (Admin only)

Admin users can access the **User Management** page from the sidebar:

1. View all user accounts with username, display name, role, and creation date
2. Click **+ New User** to create accounts with username, password, display name, and role
3. Delete non-admin users
4. Role permissions are displayed at the bottom of the page

### Authentication

GenForge requires login to access the dashboard:

- **Default accounts**: `admin`/`admin123` (full access) and `user`/`user123` (read-only)
- Sessions are persisted to `localStorage` — you stay logged in across page reloads
- Click the user badge in the sidebar footer to sign out
- **Admin role**: create/edit/delete schemas, connections, users; push data; test connections
- **User role**: view schemas, connections, connector catalog; generate previews only

---

## CLI Usage

GenForge includes a full-featured CLI for scripting and automation.

### Generate data to file

```bash
# Generate 100 ServiceNow incidents to a JSON file
genforge generate \
  --schema configs/schemas/servicenow_incident.json \
  --count 100 \
  --output incidents.json \
  --pretty

# Generate as JSONL (one record per line)
genforge generate \
  --schema configs/schemas/elasticsearch_logs.json \
  --count 1000 \
  --format jsonl \
  --output logs.jsonl

# Generate as CSV
genforge generate \
  --schema configs/schemas/prometheus_metrics.json \
  --count 500 \
  --format csv \
  --output metrics.csv
```

### Push data to a target

```bash
# Generate and push 50 records to ServiceNow
genforge push \
  --schema configs/schemas/servicenow_incident.json \
  --target configs/connections/servicenow_dev.json \
  --count 50

# With custom batch size
genforge push \
  --schema configs/schemas/servicenow_incident.json \
  --target configs/connections/servicenow_dev.json \
  --count 500 \
  --batch-size 25
```

### Run a pipeline

```bash
# Run a multi-schema pipeline (e.g., ITSM incident + change + CMDB)
genforge pipeline --config pipeline.json
```

### List connectors

```bash
genforge connectors
```

---

## Schema Specification

Schemas follow JSON Schema with GenForge-specific extensions.

### Supported Types

| Type      | Description              | Constraints                        |
|-----------|--------------------------|------------------------------------|
| `string`  | Text values              | `enum`, `pattern`, `format`        |
| `integer` | Whole numbers            | `minimum`, `maximum`, `enum`       |
| `number`  | Floating-point numbers   | `minimum`, `maximum`               |
| `boolean` | `true` / `false`         | —                                  |
| `array`   | Lists of items           | `items`, `minItems`, `maxItems`    |
| `object`  | Nested objects           | `properties`                       |

### Supported Formats

| Format      | Output example                              |
|-------------|---------------------------------------------|
| `date-time` | `2026-03-15T14:30:00.000Z`                  |
| `date`      | `2026-03-15`                                |
| `uuid`      | `a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d`    |
| `email`     | `alice.chen@acme.com`                       |
| `ipv4`      | `10.0.1.42`                                 |

### GenForge Extensions

| Extension                 | Description                                       |
|---------------------------|---------------------------------------------------|
| `x-datagen-faker`         | Use a Faker provider (e.g., `person.name`)        |
| `x-datagen-weight`        | Weighted distribution for enum values             |
| `x-datagen-distribution`  | Statistical distribution (uniform, gaussian, poisson) |
| `x-datagen-null-rate`     | Probability of generating null (0.0–1.0)          |
| `x-datagen-unique`        | Ensure unique values across records               |
| `x-datagen-ref`           | Foreign key reference to another schema's field   |
| `x-datagen-category`      | Schema category for UI grouping                   |
| `x-datagen-tags`          | Tags for filtering and search                     |

### Example Schema

```json
{
  "type": "object",
  "title": "ServiceNow Incident",
  "description": "ITSM incident records",
  "x-datagen-category": "servicenow",
  "x-datagen-tags": ["itsm", "incident"],
  "properties": {
    "number": {
      "type": "string",
      "pattern": "INC[0-9]{7}"
    },
    "short_description": {
      "type": "string",
      "x-datagen-faker": "lorem.sentence"
    },
    "priority": {
      "type": "integer",
      "enum": [1, 2, 3, 4],
      "x-datagen-weight": [5, 20, 50, 25]
    },
    "state": {
      "type": "integer",
      "enum": [1, 2, 3, 6, 7]
    },
    "assigned_to": {
      "type": "string",
      "x-datagen-faker": "person.name"
    },
    "opened_at": {
      "type": "string",
      "format": "date-time"
    }
  }
}
```

---

## Push Target Configuration

### ServiceNow

| Field        | Description                                 |
|--------------|---------------------------------------------|
| Host         | Instance URL, e.g., `dev12345.service-now.com` |
| Auth method  | `basic`, `oauth2`, or `api_key`             |
| Options      | `{"table": "incident"}` — target table name |

### Kafka

| Field        | Description                                 |
|--------------|---------------------------------------------|
| Host         | Bootstrap servers                           |
| Port         | 9092 (default)                              |
| Auth method  | `plaintext`, `sasl_plaintext`, `ssl`, `sasl_ssl` |
| Options      | `{"topic": "events", "compression": "snappy"}` |

### Elasticsearch

| Field        | Description                                 |
|--------------|---------------------------------------------|
| Host         | Cluster URL, e.g., `localhost`              |
| Port         | 9200                                        |
| Auth method  | `basic`, `api_key`, `bearer_token`          |
| Options      | `{"index": "logs-2026.03"}` — target index  |

### MongoDB

| Field        | Description                                 |
|--------------|---------------------------------------------|
| Host         | Connection URI, e.g., `localhost`           |
| Port         | 27017                                       |
| Auth method  | `basic`, `certificate`                      |
| Options      | `{"database": "mydb", "collection": "users"}` |

### VictoriaMetrics

| Field        | Description                                 |
|--------------|---------------------------------------------|
| Host         | Server URL, e.g., `localhost`               |
| Port         | 8428                                        |
| Auth method  | `bearer_token`, `basic`                     |

### Cribl

| Field        | Description                                 |
|--------------|---------------------------------------------|
| Host         | HEC endpoint URL                            |
| Auth method  | `bearer_token`, `api_key`                   |

### AWS DynamoDB

| Field        | Description                                 |
|--------------|---------------------------------------------|
| Auth method  | `aws_iam` or `api_key`                      |
| Options      | `{"table": "my-table"}` — target table name  |

### AWS Kinesis

| Field        | Description                                 |
|--------------|---------------------------------------------|
| Auth method  | `aws_iam` or `api_key`                      |
| Options      | `{"stream_name": "my-stream", "partition_key_field": "id"}` |

### AWS S3

| Field        | Description                                 |
|--------------|---------------------------------------------|
| Auth method  | `aws_iam` or `api_key`                      |
| Options      | `{"bucket": "my-bucket", "prefix": "data/", "format": "jsonl"}` |

### AWS SQS

| Field        | Description                                 |
|--------------|---------------------------------------------|
| Auth method  | `aws_iam` or `api_key`                      |
| Options      | `{"queue_url": "https://sqs.us-east-1.amazonaws.com/123/my-queue"}` |

### ClickHouse

| Field        | Description                                 |
|--------------|---------------------------------------------|
| Host         | Server URL, e.g., `localhost`               |
| Port         | 8123                                        |
| Auth method  | `basic`                                     |
| Options      | `{"database": "default", "table": "events"}` |

### Redis

| Field        | Description                                 |
|--------------|---------------------------------------------|
| Host         | Server URL, e.g., `localhost`               |
| Port         | 6379                                        |
| Auth method  | `basic`, `password`                         |
| Options      | `{"key_prefix": "test:", "data_type": "hash"}` |

### Trino

| Field        | Description                                 |
|--------------|---------------------------------------------|
| Host         | Coordinator URL                             |
| Port         | 8080                                        |
| Auth method  | `basic`, `certificate`                      |
| Options      | `{"catalog": "hive", "schema": "default", "table": "events"}` |

---

## Backend Dependencies

### Core (always required)

```bash
pip install fastapi uvicorn pydantic faker jsonschema httpx orjson
pip install "psycopg[binary]" psycopg-pool   # PostgreSQL persistence
```

### Connector-specific (install as needed)

```bash
pip install pymongo             # MongoDB
pip install confluent-kafka     # Kafka
pip install redis               # Redis
pip install trino               # Trino
pip install boto3               # AWS (DynamoDB, S3, SQS, Kinesis)
pip install prometheus_client   # Prometheus
```

### Install everything

```bash
pip install -e ".[all]"
```

> **Note:** Each connector gracefully handles missing packages — if a required library is not installed, the API returns a descriptive error with install instructions.

---

## Troubleshooting

| Symptom | Solution |
|---------|----------|
| `ModuleNotFoundError: datagen` | Run `pip install -e .` from the project root |
| API returns 500 on push | Install the connector package: `pip install pymongo`, etc. |
| Dashboard shows no data | Ensure the API is running on port 3800 |
| Connection test fails | Verify host, port, and credentials; check network access |
| WebSocket not connecting | Use `ws://localhost:3800/ws` — ensure CORS is allowed |
| `psycopg.OperationalError` | Ensure PostgreSQL is running: `brew services start postgresql@16` |
| `httpx not installed` error on push | Run `pip install httpx` (required for ServiceNow, Cribl, ClickHouse, Loki, VictoriaMetrics connectors) |
| `trino not installed` | Run `pip install trino` |
| `redis not installed` | Run `pip install redis` |
| ServiceNow 403 Business Rule error | Use valid initial states only (e.g., state `-5` for Change Requests) |
| ServiceNow 403 Data Policy error | Include mandatory fields like `close_code` and `close_notes` for resolved/closed states |
| Login fails with 401 | Verify username and password; default: `admin`/`admin123` or `user`/`user123` |
