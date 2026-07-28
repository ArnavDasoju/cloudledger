# Domain Glossary

## Billing Period

A calendar month represented as a first-of-month date (e.g. 2025-03-01). All data in CloudLedger is organized by billing period. The format used in the UI and API is `YYYY-MM` (e.g. "2025-03").

**Source:** `cloudledger/database.py:47` (billing_period_start column), `backend/server.py:45-49` (_parse_period)


## FOCUS 1.2

The FinOps Cost and Usage Specification — an industry-standard CSV format for cloud billing data. AWS produces FOCUS exports with column names like `InvoiceId`, `BillingPeriodStart`, `ServiceName`, `ResourceId`, `BilledCost`. CloudLedger auto-detects this format from the CSV headers.

**Source:** `cloudledger/ingest.py:14-37` (FOCUS_COLUMN_MAP)


## Azure Cost Export

Azure's billing CSV format, which uses different column names than FOCUS: `BillingPeriodStartDate`, `CostInBillingCurrency`, `MeterCategory`, `ResourceLocation`. CloudLedger auto-detects this format when it sees these marker columns.

**Source:** `cloudledger/ingest.py:40-59` (AZURE_COLUMN_MAP), `cloudledger/ingest.py:242-249` (_detect_format)


## Resource

A uniquely billed cloud entity identified by a `resource_id` — an ARN for AWS (e.g. `arn:aws:ec2:us-east-1:123:instance/i-abc123`) or an ARM resource path for Azure (e.g. `/subscriptions/.../providers/Microsoft.Compute/virtualMachines/my-vm`). CloudLedger stores one row per resource per billing period with its aggregated total cost.

**Source:** `cloudledger/database.py:95-120` (Resource model)


## Variance

The dollar and percentage difference in a resource's cost between two billing periods. The raw delta is `current_cost - prior_cost`. CloudLedger also computes a day-normalized delta that adjusts for different month lengths.

**Source:** `cloudledger/variance.py:305-318` (delta computation)


## Day Normalization

An adjustment that eliminates false positives from months having different numbers of days. The formula is `prior_cost_normalized = prior_cost_raw * (current_month_days / prior_month_days)`. A resource costing $100/day shows $2,800 in February and $3,100 in March — after normalization, the adjusted delta is $0.

**Source:** `cloudledger/variance.py:289-293` (day_ratio), `cloudledger/variance.py:302-318` (both deltas)


## Reason Code

A classification of why a resource's cost changed. CloudLedger assigns one of 16 reason codes to every variance row. The codes are organized into 4 buckets: planned, drift, usage, and edge cases. See the Variance Engine documentation for the full list and decision tree.

**Source:** `cloudledger/variance.py:339-379` (classification logic), `frontend/src/lib/constants.ts:29-47` (user-facing explanations)


## Confidence Score

A value between 0 and 1 indicating how reliable a classification is. Higher scores mean more evidence supports the reason code. IaC-managed resources get 0.95, edge cases get 0.90, and orphan_unknown gets 0.50.

**Source:** `cloudledger/variance.py:381-397`


## Attribution Coverage

The percentage of variance rows where `confidence_score >= 0.70`. This metric indicates what fraction of the bill change CloudLedger could confidently explain. Reported on the Close Packet.

**Source:** `cloudledger/variance.py:483-486`


## Evidence Chain

A structured JSON object attached to each variance row for audit. Records the classification inputs (costs, delta, IaC status, charge types) and each decision step the engine took. Stored in the `evidence_chain` column.

**Source:** `cloudledger/variance.py:71-157` (_build_evidence_chain), `cloudledger/database.py:160` (JSON column)


## Change Event

An infrastructure change (PR merge, terraform apply) linked to a resource_id and a date. Used by the variance engine to classify cost changes as "planned". The engine looks for events within +/-7 days of the billing period start.

**Source:** `cloudledger/database.py:123-138` (ChangeEvent model), `cloudledger/variance.py:254-279` (window)


## IaC Source

Which Infrastructure-as-Code tool manages a resource: `terraform`, `arm`, `cloudformation`, `pulumi`, or `none`. Stored on each resource row and each variance row.

**Source:** `cloudledger/database.py:110` (iac_source column), `cloudledger/normalize.py:152-197` (source detection)


## Drift

A cost change from a resource that is not managed by any IaC tool. CloudLedger sub-classifies drift into: `orphan_sdk_created` (has team tags but no IaC), `orphan_unknown` (no tags, no IaC), `legacy_untracked` (low-cost pre-IaC resource), and `non_terraform_iac` (managed by CloudFormation/CDK/Pulumi but not in uploaded Terraform state).

**Source:** `cloudledger/variance.py:348-371` (drift sub-classification)


## Close Packet

A CFO-ready document summarizing the month's cloud billing analysis. Contains an executive summary, invoice reconciliation, variance breakdown by reason code and service, key events timeline, and action items for engineering (import drift to Terraform) and finance (journal entries). Exportable as PDF.

**Source:** `cloudledger/pdf_export.py:40-311`, `backend/server.py:549-615` (/api/close-packet)


## GL Export

A General Ledger journal entry CSV. Each variance row becomes a debit or credit line with an account code derived from the service name (format: 6XXX00). Used for import into accounting systems.

**Source:** `backend/server.py:620-653` (/api/gl-export)


## Allocation

The mapping of a billing line item to a team and cost center. Attribution methods in priority order: terraform_state (confidence 0.95), tag (0.80), service_default (0.50), unattributed (0.30).

**Source:** `cloudledger/allocate.py:13-91`, `cloudledger/database.py:175-193`
