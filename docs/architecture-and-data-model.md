# Architecture and Data Model

## System Architecture

CloudLedger is a three-tier application:

- **Frontend**: Next.js single-page application with 8 screens, interactive charts (Recharts), and the Cloudly AI chat panel. Compiled to static HTML/JS for production (served by FastAPI). In development, the Next.js dev server proxies API calls to the backend.
- **Backend**: FastAPI Python server with 16+ REST endpoints for data ingestion, pipeline execution, variance analysis, exports, chat, and cloud account connection.
- **Database**: PostgreSQL with 7 tables organized in a bronze/silver/gold layer pattern.

Additional integrations: GitHub API (PR sync), Anthropic Claude API (AI assistant), MCP server (programmatic access), optional Snowflake warehouse sync.

**Source:** `backend/server.py` (FastAPI app), `frontend/src/app/page.tsx` (Next.js SPA), `cloudledger/database.py` (models), `README.md:152-164` (architecture diagram)


## Data Flow

The end-to-end pipeline:

1. **Ingest** — billing CSVs (uploaded or fetched from AWS/Azure) are parsed in 10K-row chunks, deduplicated by (invoice_id, resource_id, charge_period_start), and bulk-inserted into `raw_billing_lines`.
2. **Normalize invoices** — raw lines are aggregated by invoice_id into the `invoices` table with total cost, line count, and attribution coverage.
3. **Normalize resources** — raw lines are grouped by (resource_id, billing_period) into the `resources` table. Each resource is matched against IaC state files, tagged with team/cost_center from billing tags, and annotated with environment (production/staging/dev).
4. **Compute variance** — for each consecutive period pair, the engine loads current and prior resources, applies day normalization, evaluates the classification decision tree, and writes results to `variance_report`.
5. **Serve** — the API endpoints query the tables and return JSON to the frontend screens.

**Source:** `cloudledger/ingest.py:252-308` (step 1), `cloudledger/normalize.py:62-135` (step 2), `cloudledger/normalize.py:138-298` (step 3), `cloudledger/variance.py:160-497` (step 4), `backend/server.py` (step 5)


## Database Tables

### raw_billing_lines (Bronze)

One row per charge line from billing CSV exports. Stores the raw data as-is from the source file.

Key columns: `invoice_id`, `billing_period_start`, `billing_period_end`, `service_name`, `resource_id`, `resource_name`, `region`, `charge_type`, `billed_cost`, `tags` (JSON), `provider` (AWS or Azure).

**Source:** `cloudledger/database.py:41-73`


### invoices (Silver)

One row per invoice with aggregated totals. Created by `normalize_invoices()`.

Key columns: `invoice_id` (unique), `billing_period_start`, `total_billed_cost`, `total_line_items`, `attributed_cost`, `unattributed_cost`, `attribution_coverage_pct`, `status` (provisional).

**Source:** `cloudledger/database.py:76-92`


### resources (Silver)

One row per unique resource per billing period. Created by `normalize_resources()`.

Key columns: `resource_id`, `resource_name`, `service_name`, `region`, `team`, `cost_center`, `in_terraform_state` (boolean), `terraform_module`, `iac_source`, `environment`, `billing_period_start`, `total_cost`.

Unique constraint on (resource_id, billing_period_start).

**Source:** `cloudledger/database.py:95-120`


### change_events

Infrastructure changes linked to resources. Created by GitHub PR sync or manual seeding.

Key columns: `resource_id`, `event_type`, `event_date`, `pr_number`, `pr_title`, `pr_author`, `commit_sha`, `terraform_module`, `description`.

**Source:** `cloudledger/database.py:123-138`


### variance_report (Gold)

One row per resource per period-pair comparison. Created by `compute_variance()`.

Key columns: `resource_id`, `resource_name`, `service_name`, `team`, `prior_period_start`, `current_period_start`, `prior_cost`, `current_cost`, `delta_dollars`, `delta_pct`, `reason_code`, `confidence_score`, `evidence` (text), `evidence_chain` (JSON), `pr_number`, `iac_source`, `in_terraform_state`, `excluded` (boolean for edge cases).

Unique constraint on (resource_id, prior_period_start, current_period_start).

**Source:** `cloudledger/database.py:141-172`


### allocations

Cost allocation — maps each billing line to a team/cost center with confidence.

Key columns: `billing_line_id`, `resource_id`, `billing_period_start`, `team`, `cost_center`, `allocated_cost`, `attribution_method`, `confidence_score`.

**Source:** `cloudledger/database.py:175-193`


### logical_resources

Groups related billing line items under a logical resource (e.g. an EKS cluster with its EC2 nodes and EBS volumes).

Key columns: `logical_resource_id`, `logical_resource_name`, `resource_type`, `child_resource_id`, `relationship`, `billing_period_start`.

**Source:** `cloudledger/database.py:196-211`


## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Health check |
| GET | `/api/periods` | List available billing periods |
| POST | `/api/upload` | Upload billing CSVs |
| POST | `/api/upload/terraform` | Upload Terraform state files |
| POST | `/api/pipeline/run` | Run variance for two periods |
| POST | `/api/pipeline/run-all` | Run variance for all period pairs |
| POST | `/api/connect/aws` | Connect to AWS account |
| POST | `/api/connect/azure` | Connect to Azure account |
| GET | `/api/bill-overview` | Overview screen data |
| GET | `/api/ingestion-stats` | Ingestion screen data |
| GET | `/api/variance-by-service` | Variance screen data |
| GET | `/api/root-causes` | Root causes screen data |
| GET | `/api/close-packet` | Close packet screen data |
| GET | `/api/engineering-view` | Engineering screen data |
| GET | `/api/trends` | Trends screen data |
| GET | `/api/gl-export` | GL journal entry CSV download |
| GET | `/api/close-packet/pdf` | Close packet PDF download |
| GET | `/api/github/status` | GitHub integration status |
| POST | `/api/github/sync` | Sync GitHub PRs |
| POST | `/api/chat` | Cloudly AI assistant |

**Source:** `backend/server.py` (all endpoints)
