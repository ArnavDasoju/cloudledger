"""Tests for the cloud_connect module (AWS and Azure)."""

import csv
import os
from unittest.mock import patch, MagicMock

import pytest

from cloudledger.cloud_connect import fetch_aws_costs, fetch_azure_costs


class TestFetchAWSCosts:
    """Tests for AWS Cost Explorer integration."""

    def _mock_ce_response(self, groups):
        return {
            "ResultsByTime": [{
                "TimePeriod": {"Start": "2025-01-01", "End": "2025-02-01"},
                "Groups": groups,
            }],
        }

    @patch("boto3.Session")
    def test_basic_fetch(self, mock_session_cls):
        """Should fetch costs and produce valid FOCUS-format CSV."""
        mock_ce = MagicMock()
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.client.return_value = mock_ce

        mock_ce.get_cost_and_usage.return_value = self._mock_ce_response([
            {
                "Keys": ["Amazon EC2", "arn:aws:ec2:us-east-1:123:instance/i-abc123"],
                "Metrics": {"UnblendedCost": {"Amount": "150.50"}, "UsageQuantity": {"Amount": "744"}},
            },
            {
                "Keys": ["Amazon S3", "arn:aws:s3:::my-bucket"],
                "Metrics": {"UnblendedCost": {"Amount": "25.00"}, "UsageQuantity": {"Amount": "100"}},
            },
        ])

        try:
            paths = fetch_aws_costs("AKIAIOSFODNN7EXAMPLE", "secret", "us-east-1", 2)
            assert len(paths) == 2

            with open(paths[0]) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                assert len(rows) == 2
                assert rows[0]["ServiceName"] == "Amazon EC2"
                assert float(rows[0]["BilledCost"]) == 150.50
                assert rows[0]["ResourceId"] == "arn:aws:ec2:us-east-1:123:instance/i-abc123"
                assert rows[1]["ServiceName"] == "Amazon S3"
        finally:
            for p in paths:
                if os.path.exists(p):
                    os.unlink(p)

    @patch("boto3.Session")
    def test_skips_zero_cost(self, mock_session_cls):
        """Zero-cost resources should be omitted from the CSV."""
        mock_ce = MagicMock()
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.client.return_value = mock_ce

        mock_ce.get_cost_and_usage.return_value = self._mock_ce_response([
            {
                "Keys": ["Amazon EC2", "i-abc"],
                "Metrics": {"UnblendedCost": {"Amount": "0"}, "UsageQuantity": {"Amount": "0"}},
            },
            {
                "Keys": ["Amazon S3", "bucket-1"],
                "Metrics": {"UnblendedCost": {"Amount": "10.00"}, "UsageQuantity": {"Amount": "1"}},
            },
        ])

        try:
            paths = fetch_aws_costs("AKIAIOSFODNN7EXAMPLE", "secret", "us-east-1", 2)
            with open(paths[0]) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                assert len(rows) == 1
                assert rows[0]["ServiceName"] == "Amazon S3"
        finally:
            for p in paths:
                if os.path.exists(p):
                    os.unlink(p)

    @patch("boto3.Session")
    def test_pagination(self, mock_session_cls):
        """Should handle paginated Cost Explorer responses."""
        mock_ce = MagicMock()
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.client.return_value = mock_ce

        # Month 1: page 1 (with token) + page 2 (no token)
        # Month 2: single page
        mock_ce.get_cost_and_usage.side_effect = [
            # Month 1, page 1
            {
                "ResultsByTime": [{
                    "TimePeriod": {"Start": "2025-01-01", "End": "2025-02-01"},
                    "Groups": [{"Keys": ["EC2", "i-1"], "Metrics": {"UnblendedCost": {"Amount": "100"}, "UsageQuantity": {"Amount": "1"}}}],
                }],
                "NextPageToken": "token123",
            },
            # Month 1, page 2
            {
                "ResultsByTime": [{
                    "TimePeriod": {"Start": "2025-01-01", "End": "2025-02-01"},
                    "Groups": [{"Keys": ["S3", "bucket-1"], "Metrics": {"UnblendedCost": {"Amount": "50"}, "UsageQuantity": {"Amount": "1"}}}],
                }],
            },
            # Month 2
            {
                "ResultsByTime": [{
                    "TimePeriod": {"Start": "2025-02-01", "End": "2025-03-01"},
                    "Groups": [{"Keys": ["EC2", "i-2"], "Metrics": {"UnblendedCost": {"Amount": "110"}, "UsageQuantity": {"Amount": "1"}}}],
                }],
            },
        ]

        paths = fetch_aws_costs("AKIAIOSFODNN7EXAMPLE", "secret", "us-east-1", 2)
        try:
            with open(paths[0]) as f:
                rows = list(csv.DictReader(f))
                assert len(rows) == 2  # 2 resources from paginated month 1
        finally:
            for p in paths:
                if os.path.exists(p):
                    os.unlink(p)

    @patch("boto3.Session")
    def test_resource_name_derivation(self, mock_session_cls):
        """Resource name should be extracted from the resource ID."""
        mock_ce = MagicMock()
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.client.return_value = mock_ce

        mock_ce.get_cost_and_usage.return_value = self._mock_ce_response([
            {
                "Keys": ["Amazon EC2", "arn:aws:ec2:us-east-1:123:instance/i-xyz789"],
                "Metrics": {"UnblendedCost": {"Amount": "100"}, "UsageQuantity": {"Amount": "1"}},
            },
        ])

        try:
            paths = fetch_aws_costs("AKIAIOSFODNN7EXAMPLE", "secret", "us-east-1", 2)
            with open(paths[0]) as f:
                rows = list(csv.DictReader(f))
                assert rows[0]["ResourceName"] == "i-xyz789"
        finally:
            for p in paths:
                if os.path.exists(p):
                    os.unlink(p)


class TestFetchAzureCosts:
    """Tests for Azure Cost Management integration."""

    @patch("requests.post")
    def test_auth_failure(self, mock_post):
        """Should raise ValueError on auth failure."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Invalid client"
        mock_post.return_value = mock_resp

        with pytest.raises(ValueError, match="Azure auth failed"):
            fetch_azure_costs("sub-id", "tenant-id", "client-id", "secret", 2)

    @patch("requests.get")
    @patch("requests.post")
    def test_successful_fetch(self, mock_post, mock_get):
        """Should fetch costs and produce valid CSV."""
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {"access_token": "fake-token"}

        cost_resp = MagicMock()
        cost_resp.status_code = 200
        cost_resp.json.return_value = {
            "properties": {
                "columns": [
                    {"name": "Cost"},
                    {"name": "ResourceId"},
                    {"name": "ResourceType"},
                    {"name": "ResourceGroupName"},
                ],
                "rows": [
                    [250.50, "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1", "Microsoft.Compute/virtualMachines", "rg"],
                    [100.00, "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/sa1", "Microsoft.Storage/storageAccounts", "rg"],
                ],
            },
        }

        # Token request, then cost request for each month
        mock_post.side_effect = [token_resp, cost_resp, token_resp, cost_resp]

        try:
            paths = fetch_azure_costs("sub-id", "tenant-id", "client-id", "secret", 2)
            assert len(paths) == 2

            with open(paths[0]) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                assert len(rows) == 2
                assert float(rows[0]["CostInBillingCurrency"]) == 250.50
                assert "vm-1" in rows[0]["ResourceName"]
        finally:
            for p in paths:
                if os.path.exists(p):
                    os.unlink(p)

    @patch("requests.post")
    def test_403_error_message(self, mock_post):
        """Should provide helpful error for 403 Forbidden."""
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {"access_token": "fake-token"}

        cost_resp = MagicMock()
        cost_resp.status_code = 403
        cost_resp.text = "Forbidden"

        mock_post.side_effect = [token_resp, cost_resp]

        with pytest.raises(ValueError, match="Cost Management Reader"):
            fetch_azure_costs("sub-id", "tenant-id", "client-id", "secret", 2)

    @patch("requests.get")
    @patch("requests.post")
    def test_skips_zero_cost_azure(self, mock_post, mock_get):
        """Zero-cost rows should be omitted."""
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.json.return_value = {"access_token": "fake-token"}

        cost_resp = MagicMock()
        cost_resp.status_code = 200
        cost_resp.json.return_value = {
            "properties": {
                "columns": [{"name": "Cost"}, {"name": "ResourceId"}, {"name": "ResourceType"}, {"name": "ResourceGroupName"}],
                "rows": [
                    [0, "/sub/rg/providers/Microsoft.Compute/vm/vm-free", "Microsoft.Compute/virtualMachines", "rg"],
                    [99.00, "/sub/rg/providers/Microsoft.Compute/vm/vm-paid", "Microsoft.Compute/virtualMachines", "rg"],
                ],
            },
        }

        mock_post.side_effect = [token_resp, cost_resp, token_resp, cost_resp]

        try:
            paths = fetch_azure_costs("sub-id", "tenant-id", "client-id", "secret", 2)
            with open(paths[0]) as f:
                rows = list(csv.DictReader(f))
                assert len(rows) == 1
        finally:
            for p in paths:
                if os.path.exists(p):
                    os.unlink(p)
