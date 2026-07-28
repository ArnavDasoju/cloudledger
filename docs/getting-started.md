# Getting Started

## How do I connect my AWS account?

On the Upload screen, click the **AWS** tab. Enter your IAM Access Key ID and Secret Access Key. Optionally set a region (defaults to us-east-1). Select how many months of history to pull (2-12).

The IAM user needs the `ce:GetCostAndUsage` permission. CloudLedger calls the AWS Cost Explorer API with GROUP BY on SERVICE and RESOURCE_ID to get per-resource costs.

Credentials are used for the current session only and are not stored on the server. They are sent to the backend over HTTPS, used to call the AWS API, and then discarded.

**Source:** `backend/server.py:758-762` (AWSConnectRequest validation), `cloudledger/cloud_connect.py:13-125` (fetch_aws_costs), `frontend/src/app/page.tsx:388-408` (AWS form)


## How do I connect my Azure account?

On the Upload screen, click the **Azure** tab. Enter your Subscription ID, Tenant ID (Directory ID), Client ID (Application ID), and Client Secret.

You need an App Registration in Microsoft Entra ID (Azure AD) with the **Cost Management Reader** role assigned on the subscription. The credentials use OAuth2 client_credentials flow to get an access token, then query the Azure Cost Management API.

Where to find these values:
- **Subscription ID**: Azure Portal > Subscriptions > Overview
- **Tenant ID**: Azure Portal > Microsoft Entra ID > Overview
- **Client ID**: Azure Portal > App registrations > Your app > Overview
- **Client Secret**: App registrations > Certificates & secrets > Client secrets > Value (not Secret ID)

**Source:** `backend/server.py:764-769` (AzureConnectRequest validation), `cloudledger/cloud_connect.py:128-307` (fetch_azure_costs), `frontend/src/app/page.tsx:410-435` (Azure form)


## How do I upload billing CSVs manually?

On the Upload screen, click the **Upload Files** tab. Add at least 2 CSV files (one per billing month) and one Terraform state file.

CloudLedger accepts two CSV formats and auto-detects which one you're using:

- **AWS FOCUS 1.2** — identified by columns like `BillingPeriodStart`, `ServiceName`, `BilledCost`
- **Azure Cost Export** — identified by columns like `BillingPeriodStartDate`, `CostInBillingCurrency`, `MeterCategory`

You can upload up to 20 CSV files at once. Each file can be up to 100MB (configurable via MAX_UPLOAD_SIZE_MB).

**Source:** `cloudledger/ingest.py:242-249` (format auto-detection), `backend/server.py:104-140` (upload endpoint)


## Do I need a Terraform state file?

A Terraform state file is optional but strongly recommended. Without it, CloudLedger cannot determine which resources are managed by Infrastructure-as-Code, so all resources will be classified as drift variants (orphan_unknown, orphan_sdk_created, etc.) rather than planned or steady_state.

Upload a `.tfstate` or `.json` file on the Upload screen. CloudLedger parses it to extract resource identifiers (id, arn, resource_id attributes) and uses them to match against billed resources.

**Source:** `cloudledger/terraform.py:7-45` (parser), `cloudledger/normalize.py:236-250` (matching logic)


## How many months of data do I need?

You need at least **2 billing periods** (months). The variance engine compares the current month against the prior month. With only 1 month, there's nothing to compare against.

If you upload more than 2 months, CloudLedger runs variance analysis for every consecutive pair. For example, 6 months produces 5 variance comparisons, enabling the Trends screen to show cost trajectories over time.

When connecting directly to AWS or Azure, you can select 2-12 months of history.

**Source:** `backend/server.py:976-1009` (run_pipeline_all), `frontend/src/app/page.tsx:277-278` (period validation)


## How do I run the analysis pipeline?

After uploading your data, click **Run Pipeline** (for CSV uploads) or **Connect & Analyze** (for cloud account connection). The pipeline runs 4 steps:

1. **Upload** — billing CSVs are parsed, deduplicated, and inserted into the database
2. **Terraform** — state file is parsed and resource identifiers are extracted
3. **Normalize** — billing lines are aggregated into invoices and resources, matched against IaC state
4. **Variance** — month-over-month comparison is computed with day normalization and reason codes

After the pipeline completes, all 8 analysis screens become available in the navigation bar.

**Source:** `backend/server.py:175-198` (pipeline/run endpoint), `frontend/src/app/page.tsx:266-296` (run function)
