# Screens and Navigation

## How is the application organized?

CloudLedger has 8 screens accessed via the top navigation bar. The Upload screen is always available. The remaining 7 screens appear after you run the analysis pipeline.

**Source:** `frontend/src/app/page.tsx:15-87` (TopNav), `frontend/src/lib/constants.ts:13-16` (SCREEN_NAMES)


## What does the Upload screen show?

The Upload screen is the starting point. It offers three modes:

- **Upload Files** — drag-and-drop or browse for billing CSVs (2+ months) and a Terraform state file
- **AWS** — enter IAM credentials to pull data directly from AWS Cost Explorer
- **Azure** — enter Service Principal credentials to pull from Azure Cost Management API

Each mode has a progress stepper showing the pipeline stages. After the pipeline completes, the app navigates to the Overview screen.

**Source:** `frontend/src/app/page.tsx:250-654` (UploadScreen component)


## What does the Overview screen show?

The Overview screen provides a high-level month-over-month comparison:

- **4 KPI cards**: prior month spend, current month spend, variance delta, percentage change
- **Horizontal bar chart**: variance broken down by cloud service (e.g. Amazon EC2, S3, RDS), sorted by absolute impact

This is the "bill arrives" view — the first thing a finance controller sees.

**Source:** `frontend/src/app/page.tsx:658-729` (OverviewScreen), `backend/server.py:203-224` (/api/bill-overview)


## What does the Ingestion screen show?

The Ingestion screen reports data quality and matching results:

- **Period breakdown**: how many rows, resources, and total cost were parsed per billing month
- **Terraform matching**: percentage of resources found in the .tfstate file, by count and by cost
- **Team attribution**: percentage of resources with a "team" tag in billing data
- **Data quality checks**: 4 dot indicators for missing resource IDs, missing service names, zero-cost lines, and negative cost lines
- **Service coverage table**: per-service row count, cost, resource count, and Terraform match rate
- **Top unmatched resources**: the 5 highest-cost resources not found in Terraform state

**Source:** `frontend/src/app/page.tsx:742-983` (IngestionScreen), `backend/server.py:229-378` (/api/ingestion-stats)


## What does the Variance screen show?

The Variance screen shows every resource that changed cost:

- **4 KPI cards**: net change, total increases, total decreases, absolute variance
- **Service table**: prior cost, current cost, delta, and percentage change per service
- **Reason code filter**: sidebar with clickable badges that filter the resource table by reason code
- **Resource detail table**: scrollable table with resource name, service, prior/current cost, delta, percentage, and reason code badge
- **Expandable evidence rows**: click any resource to see its full resource ID, IaC status, cost breakdown bar, evidence string, and a plain-English explanation of why it received that reason code

**Source:** `frontend/src/app/page.tsx:987-1199` (VarianceScreen), `backend/server.py:383-467` (/api/variance-by-service)


## What does the Root Causes screen show?

The Root Causes screen groups variance into 4 high-level buckets:

- **Planned**: approved infrastructure changes (IaC-managed + matching change event)
- **Drift**: resources not managed by IaC (orphan_sdk_created, orphan_unknown, legacy_untracked, non_terraform_iac)
- **Usage**: organic changes (usage_growth, new_resource, removed_resource, price_change, steady_state)
- **Edge Cases**: billing patterns (Savings Plans, Reserved Instances, credits, marketplace, spot, data transfer)

Each bucket shows total dollar amount, resource count, and the top 5 resources by impact.

**Source:** `backend/server.py:472-544` (/api/root-causes), `backend/server.py:72-78` (bucket definitions)


## What does the Close Packet screen show?

The Close Packet screen is a CFO-ready summary with:

- **Executive KPIs**: prior cost, current cost, net variance, total variance
- **Variance by reason code**: each code with its dollar amount and top 3 contributing resources
- **Action items**: top 5 drift resources that need engineering follow-up (import to Terraform or investigate)
- **Export buttons**: download as PDF close packet or GL journal entry CSV

**Source:** `backend/server.py:549-615` (/api/close-packet), `backend/server.py:620-675` (GL + PDF export)


## What does the Engineering screen show?

The Engineering screen focuses on IaC coverage and team attribution:

- **Managed vs unmanaged**: resource counts and cost split by IaC status
- **Planned vs drift**: totals for approved changes vs unmanaged resource drift
- **Drift inventory**: full table of drift resources with service, cost, delta, reason code, team, and IaC source
- **IaC source breakdown**: resource counts and cost by source (terraform, arm, cloudformation, pulumi, none)
- **Team breakdown**: resource count, cost, managed count, and delta per team tag

**Source:** `backend/server.py:680-751` (/api/engineering-view)


## What does the Trends screen show?

The Trends screen provides multi-period analysis:

- **Cost trend line chart**: total spend per billing period over time (Recharts LineChart)
- **Per-service trends**: cost trajectory per cloud service across all uploaded periods
- **Variance history**: net change and absolute variance per period pair, broken down by reason code
- **Anomaly table**: resources with >50% cost change AND >$500 absolute delta, sorted by impact

This screen requires 3+ billing periods to be useful.

**Source:** `backend/server.py:881-973` (/api/trends)


## What is the Cloudly assistant?

Cloudly is an AI chat assistant accessible via the "Ask Cloudly" button in the top navigation. It slides open as a panel on the right side of the screen.

Cloudly can answer two types of questions:
- **Product questions** — how CloudLedger works, what reason codes mean, how variance is computed. These are answered using a RAG knowledge base of product documentation.
- **Data questions** — what your specific billing data shows, which resources changed, what to investigate. These are answered using the live data from your current screen.

Each screen has 3 suggested questions tailored to that view. Conversation history is maintained within the panel session.

**Source:** `frontend/src/app/page.tsx:1782-1930` (CloudlyPanel), `backend/server.py:1081-1120` (/api/chat), `backend/agent.py` (RAG agent), `frontend/src/lib/constants.ts:49-57` (suggested questions)
