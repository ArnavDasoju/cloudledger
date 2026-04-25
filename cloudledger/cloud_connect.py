"""Fetches billing data directly from AWS or Azure accounts."""

import csv
import io
import logging
import tempfile
from datetime import date, timedelta
from typing import Dict, List

logger = logging.getLogger(__name__)


def fetch_aws_costs(
    access_key: str,
    secret_key: str,
    region: str = "us-east-1",
    months: int = 2,
) -> List[str]:
    """Fetch billing data from AWS Cost Explorer and return paths to CSV files.

    Creates one CSV per month in FOCUS-compatible format.
    Returns list of temp file paths.
    """
    import boto3

    session = boto3.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    ce = session.client("ce")

    # Calculate date ranges for the requested months
    today = date.today().replace(day=1)
    csv_paths = []

    for i in range(months, 0, -1):
        # Go back i months
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        period_start = date(y, m, 1)

        # End of month
        if m == 12:
            period_end = date(y + 1, 1, 1)
        else:
            period_end = date(y, m + 1, 1)

        logger.info("Fetching AWS costs for %s to %s", period_start, period_end)

        # Get cost and usage grouped by service and resource
        results = []
        next_token = None

        while True:
            kwargs = {
                "TimePeriod": {
                    "Start": period_start.isoformat(),
                    "End": period_end.isoformat(),
                },
                "Granularity": "MONTHLY",
                "Metrics": ["UnblendedCost", "UsageQuantity"],
                "GroupBy": [
                    {"Type": "DIMENSION", "Key": "SERVICE"},
                    {"Type": "DIMENSION", "Key": "RESOURCE_ID"},
                ],
            }
            if next_token:
                kwargs["NextPageToken"] = next_token

            resp = ce.get_cost_and_usage(**kwargs)
            results.extend(resp.get("ResultsByTime", []))
            next_token = resp.get("NextPageToken")
            if not next_token:
                break

        # Convert to FOCUS-compatible CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "InvoiceId", "BillingPeriodStart", "BillingPeriodEnd",
            "ServiceName", "ResourceId", "ResourceName",
            "Region", "ChargeType", "BilledCost", "Tags",
        ])

        invoice_id = f"AWS-{period_start.strftime('%Y-%m')}"
        for result in results:
            start = result["TimePeriod"]["Start"]
            end = result["TimePeriod"]["End"]
            for group in result.get("Groups", []):
                keys = group["Keys"]
                service = keys[0] if len(keys) > 0 else ""
                resource_id = keys[1] if len(keys) > 1 else ""
                cost = float(group["Metrics"]["UnblendedCost"]["Amount"])

                if cost == 0:
                    continue

                # Derive resource name from resource ID; use service name as fallback
                if not resource_id:
                    resource_id = f"{service.lower().replace(' ', '-')}-aggregate"
                resource_name = resource_id.split("/")[-1] if "/" in resource_id else resource_id.split(":")[-1] if ":" in resource_id else resource_id
                if not resource_name:
                    resource_name = resource_id

                writer.writerow([
                    invoice_id, start, end,
                    service, resource_id, resource_name,
                    region, "Usage", f"{cost:.6f}", "{}",
                ])

        # Write to temp file
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", prefix=f"aws_{period_start.strftime('%Y_%m')}_",
            delete=False,
        )
        tmp.write(output.getvalue())
        tmp.close()
        csv_paths.append(tmp.name)
        logger.info("Wrote %s", tmp.name)

    return csv_paths


def fetch_azure_costs(
    subscription_id: str,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    months: int = 2,
) -> List[str]:
    """Fetch billing data from Azure Cost Management API.

    Creates one CSV per month in Azure Cost Export compatible format.
    Returns list of temp file paths.
    """
    import requests as req

    # Get access token
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    try:
        token_resp = req.post(token_url, data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://management.azure.com/.default",
        }, timeout=30)
    except req.exceptions.RequestException as e:
        raise ValueError(f"Azure auth request failed: {e}")

    if token_resp.status_code != 200:
        raise ValueError(f"Azure auth failed: {token_resp.text[:300]}")

    token_data = token_resp.json()
    if "access_token" not in token_data:
        raise ValueError(f"Azure auth response missing access_token: {token_resp.text[:300]}")

    access_token = token_data["access_token"]
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    today = date.today().replace(day=1)
    csv_paths = []

    for i in range(months, 0, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        period_start = date(y, m, 1)
        if m == 12:
            period_end = date(y + 1, 1, 1) - timedelta(days=1)
        else:
            period_end = date(y, m + 1, 1) - timedelta(days=1)

        logger.info("Fetching Azure costs for %s to %s", period_start, period_end)

        # Query Cost Management API
        cost_url = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.CostManagement/query?api-version=2023-11-01"
        body = {
            "type": "ActualCost",
            "timeframe": "Custom",
            "timePeriod": {
                "from": period_start.isoformat() + "T00:00:00+00:00",
                "to": period_end.isoformat() + "T23:59:59+00:00",
            },
            "dataset": {
                "granularity": "None",
                "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
                "grouping": [
                    {"type": "Dimension", "name": "ResourceId"},
                    {"type": "Dimension", "name": "ResourceType"},
                    {"type": "Dimension", "name": "ResourceGroupName"},
                ],
            },
        }

        # Fetch all pages
        all_rows = []
        all_columns = []
        next_link = None

        while True:
            try:
                if next_link:
                    resp = req.get(next_link, headers=headers, timeout=120)
                else:
                    resp = req.post(cost_url, headers=headers, json=body, timeout=120)
            except req.exceptions.RequestException as e:
                raise ValueError(f"Azure Cost Management API request failed: {e}")

            if resp.status_code == 401:
                raise ValueError("Azure API returned 401 Unauthorized. Check that the App Registration has 'Cost Management Reader' role on the subscription.")
            if resp.status_code == 403:
                raise ValueError("Azure API returned 403 Forbidden. The App Registration needs 'Cost Management Reader' or 'Reader' role on the subscription.")
            if resp.status_code == 429:
                raise ValueError("Azure API rate limited (429). Try again in a few minutes or reduce the number of months.")
            if resp.status_code != 200:
                raise ValueError(f"Azure Cost Management API error {resp.status_code}: {resp.text[:300]}")

            data = resp.json()
            props = data.get("properties", {})

            if not all_columns:
                all_columns = [c["name"] for c in props.get("columns", [])]

            all_rows.extend(props.get("rows", []))
            next_link = props.get("nextLink")
            if not next_link:
                break

        logger.info("Fetched %d rows for %s", len(all_rows), period_start.strftime("%Y-%m"))

        # Convert to CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "InvoiceId", "BillingPeriodStartDate", "BillingPeriodEndDate",
            "ResourceId", "ResourceName", "MeterCategory",
            "ResourceLocation", "ChargeType", "CostInBillingCurrency", "Tags",
        ])

        invoice_id = f"AZ-{period_start.strftime('%Y-%m')}"
        for row in all_rows:
            # Safely map columns to values
            row_dict = {}
            for idx, col in enumerate(all_columns):
                row_dict[col] = row[idx] if idx < len(row) else None

            try:
                cost = float(row_dict.get("Cost") or row_dict.get("PreTaxCost") or 0)
            except (TypeError, ValueError):
                continue
            if cost == 0:
                continue

            resource_id = str(row_dict.get("ResourceId") or "")
            resource_type = str(row_dict.get("ResourceType") or "")
            resource_group = str(row_dict.get("ResourceGroupName") or "")

            # Skip subscription-level charges with no resource ID
            if not resource_id:
                resource_id = f"azure-{resource_type.lower().replace('/', '-') or 'subscription'}-aggregate"

            resource_name = resource_id.split("/")[-1] if "/" in resource_id else resource_id

            writer.writerow([
                invoice_id,
                period_start.isoformat(),
                period_end.isoformat(),
                resource_id,
                resource_name,
                resource_type,
                "",  # location not available in this query
                "Usage",
                f"{cost:.6f}",
                "{}",
            ])

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", prefix=f"azure_{period_start.strftime('%Y_%m')}_",
            delete=False,
        )
        tmp.write(output.getvalue())
        tmp.close()
        csv_paths.append(tmp.name)
        logger.info("Wrote %s with %d rows", tmp.name, len(all_rows))

    return csv_paths
