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

**Extracting schema from a live application:**
1. Click **Extract from app** in the Schema Studio toolbar
2. Select an existing **connection** from the dropdown, or click **+ New** to create one inline — only connectors that support schema extraction are shown (ServiceNow, Elasticsearch, PostgreSQL, MongoDB, ClickHouse, Trino)
3. Enter the **target name** (table, index, or collection depending on the connector type) — the label updates automatically based on the connector
4. Click **Extract** — GenForge connects to the live instance and auto-discovers the schema
5. Review the extracted schema preview, adjust the **name** and **category** if needed
6. Click **Save schema** to add it to your workspace

The extracted schema maps native data types to JSON Schema types (e.g., PostgreSQL `timestamp with time zone` → `{"type":"string","format":"date-time"}`). **Automatic enrichment:** extracted schemas are post-processed to add intelligent data generation hints based on field names:

- **Faker providers** — `name` → `person.name`, `email` → `format: email`, `phone` → `phone.number`, `city` → `address.city`, `company` → `company.name`, `description` → `lorem.sentence`, etc.
- **Enums** — `priority` → `["1 - Critical", "2 - High", ...]`, `state` → `["New", "In Progress", ...]`, `category`, `severity`, `impact`, `urgency`, `active` (true/false)
- **Patterns** — `number` → `INC[0-9]{7}` (ticket number format)
- **Formats** — `ip_address` → `ipv4`, `url` → `uri`, `uuid` → `uuid`

Fields that already have `x-datagen-faker`, `enum`, `pattern`, or recognized `format` values are left untouched. You can further refine the extracted schema with `x-datagen-*` extensions.

**Deleting a schema (admin only):**
1. Click any schema card to open the detail modal
2. Click **Delete** (red button, bottom-left) — only visible to admin users
3. Confirm the deletion in the dialog

**Inspecting a schema:**
- Click any schema card to view its full JSON definition
- Field names are displayed as chips on each card
- Click **Use in generator** to jump to the Generate page
- Use **category filter tabs** to filter schemas by category

> **Note:** All dropdown lists throughout the dashboard (connections, schemas, connector types, auth methods, categories, targets) are sorted alphabetically for easy navigation.

### Connections

Configure connections to external push targets.

**Adding a connection:**
1. Click **+ New connection**
2. Select the **connector type** (ServiceNow, Kafka, Elasticsearch, etc.) — connector-specific settings appear automatically
3. Fill in **host** and **port**
4. Select an **auth method** — credential fields update dynamically:
   - **Basic auth** → Username + Password
   - **API key** → API Key Header + API Key Value
   - **OAuth 2.0** → Client ID + Client Secret + Token URL
   - **Bearer token** → Bearer Token
   - **AWS IAM** → Access Key ID + Secret Access Key + AWS Region
5. Review the **connector settings** if shown (e.g., SSL, database name, compression) — only settings that affect connectivity appear here; push targets like table, index, or topic are selected at push time
6. Click **Create**

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

### Schema Intelligence

The **Schema Intelligence** page (under the Intelligence section in the sidebar) provides automated schema quality analysis.

**Banner & actions:**
- **Load schema** — import a JSON Schema file from disk for one-off analysis (supports raw and wrapped formats)
- **Download report** — export the current analysis as a formatted text report (available after running an analysis)

**Portfolio overview (always visible):**
- **Portfolio Quality Score** — aggregate quality score across all schemas (0–100)
- **Schema Coverage** — total schemas, total fields, avg fields per schema, category count
- **Quality Distribution** — breakdown into excellent (≥80), good (50–79), and needs-work (<50)

**Per-schema analysis:**
1. Click any schema in the left panel — analysis runs automatically
2. Results appear on the right:
   - **Score breakdown** — overall score, total fields, enums, fakers, weighted fields (5-column grid)
   - **Insights & Recommendations** — actionable tips to improve data realism
   - **Field Profiling** — per-field table with type, score, traits (weighted, faker, pattern, etc.), and warnings
   - **Type Distribution** — visual bars showing field type proportions, plus description/tag/field quality sub-scores
3. Click **Re-run analysis** to refresh, or **Download report** for an exportable text file

The quality score considers: description, tags, field types, formats, enums, weights, faker providers, patterns, distributions, null rates, uniqueness, dependencies, bounds, future-date, and date-pair constraints.

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
- **User role**: view schemas, connections, connector catalog, ML analysis; generate previews only

**Self-service registration:**
1. Click **Create an account** on the login screen
2. Enter username (required), email (optional), display name (optional), and password (min 6 characters)
3. Confirm password and click **Create Account**
4. You are automatically signed in after successful registration (assigned the "user" role)

**Forgot password:**
1. Click **Forgot password?** on the login screen
2. Enter your username or email address
3. Enter a new password (min 6 characters) and confirm it
4. Click **Reset Password** — you’ll be redirected back to the login screen

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

---

## Testing

GenForge includes a comprehensive test suite with 273+ tests across 9 test files:

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test categories
python -m pytest tests/test_engine.py -v          # Engine & pipeline
python -m pytest tests/test_connectors.py -v       # Connectors & auth
python -m pytest tests/test_models.py -v           # Pydantic models
python -m pytest tests/test_edge_cases.py -v       # Edge cases & boundaries
python -m pytest tests/test_property_based.py -v   # Hypothesis property-based
python -m pytest tests/test_negative.py -v         # Negative / invalid inputs
python -m pytest tests/test_mutation.py -v         # Mutation tests
python -m pytest tests/test_enrichment.py -v       # Schema enrichment
python -m pytest tests/test_property_extended.py -v # Extended property-based
```

### Test categories

| File | Category | Description |
|------|----------|-------------|
| `test_engine.py` | Unit | Generators, schema parser, time-series, pipeline |
| `test_connectors.py` | Unit | Connector base class, registry, auth provider, metadata |
| `test_models.py` | Unit | Pydantic request/response model validation |
| `test_edge_cases.py` | Boundary | Empty schemas, zero counts, large batches, deep nesting |
| `test_property_based.py` | Property | Hypothesis-based invariants for generators & parser |
| `test_negative.py` | Negative | Invalid inputs, malformed schemas, error paths |
| `test_mutation.py` | Mutation | Schema changes produce different outputs |
| `test_enrichment.py` | Integration | Schema enrichment function correctness |
| `test_property_extended.py` | Property | Enrichment invariants, pipeline integrity, timeseries |
