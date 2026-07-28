# Exports and Integrations

## How do I export the close packet as PDF?

On the Close Packet screen, click the **PDF Export** button. CloudLedger generates a multi-page PDF containing:

- **Executive summary**: total spend, delta, percentage change, attribution coverage, count of drift resources needing follow-up
- **Invoice reconciliation table**: invoice number, billed amount, prior month amount, reconciliation status, attribution coverage percentage
- **Variance by reason code table**: each reason code with dollar amount, share of total variance, and description
- **Variance by service table**: top 6 services by absolute variance
- **Key events timeline**: recent change events (PR merges, terraform applies) with dates and authors
- **Action items**: engineering action items (drift resources to import to Terraform) and finance action items (journal entries to post for planned, drift, and usage changes)

The PDF is generated server-side using ReportLab and returned as a file download. Temporary files are cleaned up automatically after the response is sent.

**Source:** `cloudledger/pdf_export.py:40-311` (PDF generation), `backend/server.py:658-675` (/api/close-packet/pdf endpoint)


## How do I export GL journal entries?

On the Close Packet screen, click the **GL Export** button. CloudLedger generates a CSV file with one row per variance entry, formatted for import into accounting systems like QuickBooks or NetSuite.

CSV columns:
- **Date** — billing period start date (YYYY-MM-DD)
- **Account** — derived account code from the service name (format: 6XXX00 where XXX is the first 3 characters of the service name)
- **Description** — resource name and reason code
- **Debit** — positive delta amount (cost increases)
- **Credit** — negative delta amount (cost decreases)
- **Reason** — the variance reason code
- **Service** — the cloud service name

**Source:** `backend/server.py:620-653` (/api/gl-export endpoint)


## How does the GitHub integration work?

CloudLedger can sync merged pull requests from a GitHub repository to identify planned infrastructure changes. This allows the variance engine to reclassify cost changes from "drift" to "planned" when a matching PR is found.

To configure it, set `GITHUB_TOKEN` and `GITHUB_REPO` (format: `owner/repo`) in your `.env` file. Then use the GitHub sync button on the Engineering screen or call the `/api/github/sync` endpoint.

The sync process:
1. Fetches closed+merged PRs from the GitHub API
2. Filters to PRs that modify `.tf` files
3. Parses resource and module declarations from the PR diffs
4. Matches changed resources to billing resources by Terraform module path or resource name pattern
5. Creates `change_events` rows in the database

When the variance engine runs, resources with matching change events within +/-7 days of the billing period are classified as `planned` instead of drift.

**Source:** `cloudledger/github_sync.py:25-231` (full sync pipeline), `cloudledger/variance.py:254-279` (change event window), `cloudledger/variance.py:346-347` (planned classification)


## What is the MCP server?

CloudLedger includes an MCP (Model Context Protocol) server that exposes 6 tools for programmatic access from any MCP-compatible client, such as Claude Desktop.

Available tools:
- **get_billing_overview** — high-level spend comparison between two months
- **get_variance_by_resource** — resource-level variance details sorted by impact
- **get_root_cause_summary** — variance breakdown by root cause category
- **get_iac_coverage** — IaC coverage metrics with top unmanaged resources
- **get_available_periods** — list all uploaded billing periods with totals
- **get_anomalies** — resources with unusually large cost changes (configurable thresholds)

To use it, add this to your MCP client configuration:
```json
{
  "mcpServers": {
    "cloudledger": {
      "command": "/path/to/cloudledger/venv/bin/python",
      "args": ["-m", "cloudledger.mcp_server"]
    }
  }
}
```

**Source:** `cloudledger/mcp_server.py:22-249` (6 tool definitions)


## What is the Cloudly AI assistant?

Cloudly is an embedded AI chat assistant that answers questions about your billing data and about how CloudLedger works. It uses a RAG (Retrieval-Augmented Generation) system that retrieves relevant product documentation before answering, and combines that with live data from the screen you're currently viewing.

Cloudly uses the Claude claude-sonnet-4-6 model via the Anthropic API. The API key is configured in `.env` as `ANTHROPIC_API_KEY`. Conversations are stored in the browser session only — they are not persisted on the server.

Each screen has tailored suggested questions. Answers include numbered citation badges `[1] [2]` that link back to the source documentation used to generate the response.

**Source:** `backend/agent.py` (RAG agent), `backend/rag.py` (vector retrieval), `backend/server.py:1081-1120` (/api/chat endpoint), `frontend/src/app/page.tsx:1782-1930` (chat panel with citations)
