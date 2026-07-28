# Product Overview

## What is CloudLedger?

CloudLedger is a cloud billing variance analysis tool. It automates the month-end cloud close process — the work of tracing every dollar of cost change to a specific engineering decision, infrastructure drift event, or billing pattern.

The tool is built for two roles: finance controllers who need to close the books and explain the cloud bill to their CFO, and platform engineers who need visibility into which of their changes moved the bill and where drift is accumulating.

**Source:** `README.md`, `frontend/src/lib/constants.ts:18-27`


## What problem does it solve?

Every month, cloud bills change. Nobody can explain why. Engineering shipped a dozen changes, but nobody tracks which change cost what. The finance controller spends days manually reconciling spreadsheets to close the books.

CloudLedger fixes this by ingesting billing data from AWS or Azure, matching every billed resource against your Infrastructure-as-Code state, classifying each cost change with a reason code, and generating a CFO-ready close packet in minutes.

**Source:** `frontend/src/app/page.tsx:117-123` (landing page copy), `README.md:11-22`


## What cloud providers are supported?

CloudLedger supports **AWS** and **Azure**.

For AWS, it accepts FOCUS 1.2 billing CSV exports or can connect directly to an AWS account using IAM Access Key + Secret Key to pull data from the Cost Explorer API.

For Azure, it accepts Azure Cost Export CSVs or can connect directly using a Service Principal (App Registration) with Cost Management Reader role to pull data from the Cost Management API.

**Source:** `cloudledger/cloud_connect.py:13-125` (AWS), `cloudledger/cloud_connect.py:128-307` (Azure), `cloudledger/ingest.py:14-59` (format detection)


## What IaC tools are supported?

CloudLedger supports four Infrastructure-as-Code tools for matching billed resources to managed infrastructure:

- **Terraform** — parses `.tfstate` JSON files, extracts resource IDs from `id`, `arn`, and `*resource_id` attributes
- **ARM Templates** — parses Azure ARM template JSON, maps resource `id` and `name` to metadata
- **CloudFormation** — parses CloudFormation template JSON, maps logical IDs to resource types
- **Pulumi** — parses Pulumi state JSON, maps resource `id`, `urn`, and `arn` from outputs

The frontend upload currently supports Terraform state files. ARM, CloudFormation, and Pulumi are available through the `normalize_resources()` function API.

**Source:** `cloudledger/terraform.py:7-45`, `cloudledger/arm.py:7-26`, `cloudledger/cloudformation.py:7-23`, `cloudledger/pulumi.py:7-36`, `cloudledger/normalize.py:138-197`


## What are the main features?

- **Billing data ingestion** from CSV uploads or direct AWS/Azure account connection
- **Auto-detection** of AWS FOCUS 1.2 vs Azure Cost Export format from CSV headers
- **IaC matching** against Terraform, ARM, CloudFormation, and Pulumi state files
- **Day-normalized variance** that adjusts for different month lengths to eliminate false positives
- **16 reason codes** classifying every cost change (planned, drift, usage growth, edge cases, etc.)
- **Evidence chains** providing a structured audit trail for every classification
- **Confidence scoring** from 0.50 to 0.95 indicating classification reliability
- **8 analysis screens** (Upload, Overview, Ingestion, Variance, Root Causes, Close Packet, Engineering, Trends)
- **PDF close packet** generation for CFO review
- **GL journal entry CSV** export for accounting systems
- **GitHub CI/CD integration** syncing merged PRs that touch `.tf` files to reclassify drift as planned
- **Cloudly AI assistant** with RAG-powered answers about the product and your billing data
- **MCP server** exposing 6 tools for programmatic access from any MCP-compatible client
- **Snowflake sync** (optional) for warehouse-based analytics

**Source:** `backend/server.py` (16+ API endpoints), `cloudledger/variance.py` (engine), `cloudledger/mcp_server.py` (MCP), `cloudledger/pdf_export.py` (PDF), `cloudledger/github_sync.py` (GitHub)
