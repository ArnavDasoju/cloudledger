"""Syncs GitHub PR data into change_events for planned variance classification."""

import logging
import re
from datetime import date, timedelta
from typing import Dict, List, Optional

import requests

from cloudledger.config import GITHUB_TOKEN, GITHUB_REPO
from cloudledger.database import get_db, ChangeEvent, Resource

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"


def _headers() -> dict:
    h = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"token {GITHUB_TOKEN}"
    return h


def fetch_terraform_prs(since_date: date, until_date: Optional[date] = None) -> List[dict]:
    """Fetch merged PRs that touch .tf files from the configured GitHub repo."""
    if not GITHUB_REPO:
        return []

    url = f"{API_BASE}/repos/{GITHUB_REPO}/pulls"
    params = {"state": "closed", "sort": "updated", "direction": "desc", "per_page": 100}

    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    if resp.status_code == 401:
        raise ValueError("Invalid GITHUB_TOKEN — check your .env")
    if resp.status_code == 404:
        raise ValueError(f"Repository '{GITHUB_REPO}' not found — check GITHUB_REPO in .env")
    resp.raise_for_status()

    tf_prs = []
    for pr in resp.json():
        if not pr.get("merged_at"):
            continue
        merged = pr["merged_at"][:10]  # "2024-03-15T..." -> "2024-03-15"
        merged_date = date.fromisoformat(merged)
        if merged_date < since_date:
            continue
        if until_date and merged_date > until_date:
            continue

        # Fetch changed files for this PR
        files_url = f"{API_BASE}/repos/{GITHUB_REPO}/pulls/{pr['number']}/files"
        files_resp = requests.get(files_url, headers=_headers(), timeout=30)
        if files_resp.status_code != 200:
            continue

        tf_files = []
        for f in files_resp.json():
            if f["filename"].endswith(".tf"):
                tf_files.append({
                    "path": f["filename"],
                    "status": f["status"],  # added, modified, removed
                    "patch": f.get("patch", ""),
                })

        if tf_files:
            tf_prs.append({
                "pr_number": str(pr["number"]),
                "title": pr["title"],
                "author": pr["user"]["login"],
                "merged_at": merged_date,
                "commit_sha": pr.get("merge_commit_sha", ""),
                "tf_files": tf_files,
            })

    return tf_prs


def parse_tf_changes(tf_files: List[dict]) -> List[dict]:
    """Extract resource identifiers and modules from terraform file diffs."""
    changes = []
    # Match resource blocks: resource "aws_instance" "name" {
    resource_pattern = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"')
    # Match module blocks: module "name" {
    module_pattern = re.compile(r'module\s+"([^"]+)"')

    for f in tf_files:
        # Derive terraform module from file path (directory)
        parts = f["path"].rsplit("/", 1)
        tf_module = parts[0] if len(parts) > 1 else "root"

        patch = f.get("patch", "")
        # Find all resource declarations in the patch
        for match in resource_pattern.finditer(patch):
            changes.append({
                "resource_type": match.group(1),
                "resource_name": match.group(2),
                "terraform_module": tf_module,
                "action": f["status"],
            })

        # If no specific resources found in patch, record the module-level change
        if not resource_pattern.search(patch):
            for match in module_pattern.finditer(patch):
                changes.append({
                    "resource_type": "module",
                    "resource_name": match.group(1),
                    "terraform_module": tf_module,
                    "action": f["status"],
                })

            # Fallback: just record the file as a module-level change
            if not module_pattern.search(patch):
                changes.append({
                    "resource_type": "terraform_file",
                    "resource_name": f["path"],
                    "terraform_module": tf_module,
                    "action": f["status"],
                })

    return changes


def match_resources_to_pr(tf_changes: List[dict], billing_period: date) -> List[str]:
    """Match terraform changes to billing resources by module and resource name."""
    matched_resource_ids = []

    with get_db() as session:
        resources = (
            session.query(Resource)
            .filter(Resource.billing_period_start == billing_period)
            .all()
        )

        for change in tf_changes:
            module = change["terraform_module"]
            rtype = change["resource_type"]
            rname = change["resource_name"]

            for r in resources:
                # Match by terraform module
                if r.terraform_module and module in r.terraform_module:
                    matched_resource_ids.append(r.resource_id)
                    continue
                # Match by resource name pattern
                if rname and r.resource_name and rname.lower() in r.resource_name.lower():
                    matched_resource_ids.append(r.resource_id)
                    continue
                # Match by resource type in service name
                if rtype and r.service_name:
                    type_map = {
                        "aws_instance": "ec2", "aws_eks_cluster": "eks",
                        "aws_rds_cluster": "rds", "aws_s3_bucket": "s3",
                        "aws_lambda_function": "lambda", "aws_lb": "load balancing",
                        "aws_cloudfront_distribution": "cloudfront",
                    }
                    svc_hint = type_map.get(rtype, "")
                    if svc_hint and svc_hint in r.service_name.lower():
                        # Loose match — same service type in same module
                        if r.terraform_module and module.split("/")[-1] in r.terraform_module:
                            matched_resource_ids.append(r.resource_id)

    return list(set(matched_resource_ids))


def sync_github_events(billing_period: str) -> Dict:
    """Main orchestrator: fetch PRs, parse changes, create change_events."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return {"error": "GITHUB_TOKEN and GITHUB_REPO must be set in .env", "prs_found": 0}

    period_date = date.fromisoformat(f"{billing_period}-01")
    # Look for PRs merged 30 days before through end of billing period
    since = period_date - timedelta(days=30)
    until = period_date + timedelta(days=31)

    prs = fetch_terraform_prs(since, until)

    events_created = 0
    resources_matched = set()

    with get_db() as session:
        # Clear existing GitHub-sourced events for this window to avoid duplicates
        session.query(ChangeEvent).filter(
            ChangeEvent.event_type == "github_pr",
            ChangeEvent.event_date >= since,
            ChangeEvent.event_date <= until,
        ).delete()

        for pr in prs:
            tf_changes = parse_tf_changes(pr["tf_files"])
            matched_ids = match_resources_to_pr(tf_changes, period_date)

            for rid in matched_ids:
                ce = ChangeEvent(
                    resource_id=rid,
                    event_type="github_pr",
                    event_date=pr["merged_at"],
                    pr_number=pr["pr_number"],
                    pr_title=pr["title"],
                    pr_author=pr["author"],
                    commit_sha=pr["commit_sha"],
                    terraform_module=tf_changes[0]["terraform_module"] if tf_changes else None,
                    description=f"PR #{pr['pr_number']}: {pr['title']}",
                )
                session.add(ce)
                events_created += 1
                resources_matched.add(rid)

            # Also create events for unmatched tf changes (module-level)
            if not matched_ids and tf_changes:
                for change in tf_changes[:3]:  # limit to avoid spam
                    ce = ChangeEvent(
                        resource_id=f"tf:{change['terraform_module']}/{change['resource_name']}",
                        event_type="github_pr",
                        event_date=pr["merged_at"],
                        pr_number=pr["pr_number"],
                        pr_title=pr["title"],
                        pr_author=pr["author"],
                        commit_sha=pr["commit_sha"],
                        terraform_module=change["terraform_module"],
                        description=f"PR #{pr['pr_number']}: {pr['title']} ({change['action']} {change['resource_type']}.{change['resource_name']})",
                    )
                    session.add(ce)
                    events_created += 1

    return {
        "prs_found": len(prs),
        "tf_prs": len(prs),
        "events_created": events_created,
        "resources_matched": len(resources_matched),
    }
