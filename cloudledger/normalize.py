"""Normalizes raw billing lines into invoices and resources tables."""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, text

from cloudledger.database import get_db, RawBillingLine, Invoice, Resource, ChangeEvent
from cloudledger.terraform import parse_terraform_state

logger = logging.getLogger(__name__)


# Patterns for identifying related resources
EKS_PATTERNS = {
    "node": [r"eks.*node", r"eks.*managed", r"i-[a-f0-9]+"],  # EC2 instances in node groups
    "volume": [r"vol-[a-f0-9]+"],  # EBS volumes attached to nodes
    "load_balancer": [r"elb", r"loadbalancer", r"nlb", r"alb"],
    "nat_gateway": [r"nat-[a-f0-9]+", r"nat gateway"],
}

RDS_PATTERNS = {
    "replica": [r"replica", r"reader"],
    "storage": [r"storage", r"ebs", r"aurora-storage"],
    "backup": [r"backup", r"snapshot"],
    "io": [r"iops", r"io1", r"io2"],
}

ENVIRONMENT_PATTERNS = {
    "production": ["prod", "production", "prd", "live"],
    "staging": ["staging", "stg", "stage", "uat", "preprod", "pre-prod"],
    "dev": ["dev", "development", "sandbox", "test", "testing"],
}


def _derive_environment(resource_name: str, tags: dict, tf_module: str) -> str:
    """Derive environment from resource name, tags, or Terraform module path."""
    # Check tags first (most reliable)
    if isinstance(tags, dict):
        env_tag = (tags.get("environment") or tags.get("env") or tags.get("Environment") or tags.get("Env") or "").lower()
        for env, patterns in ENVIRONMENT_PATTERNS.items():
            if any(p in env_tag for p in patterns):
                return env

    # Check Terraform module path
    module_lower = (tf_module or "").lower()
    for env, patterns in ENVIRONMENT_PATTERNS.items():
        if any(p in module_lower for p in patterns):
            return env

    # Check resource name
    name_lower = (resource_name or "").lower()
    for env, patterns in ENVIRONMENT_PATTERNS.items():
        if any(p in name_lower for p in patterns):
            return env

    return "other"


def normalize_invoices():
    """Aggregate raw_billing_lines by invoice_id to populate the invoices table."""
    with get_db() as session:
        results = (
            session.query(
                RawBillingLine.invoice_id,
                func.min(RawBillingLine.billing_period_start).label("period_start"),
                func.max(RawBillingLine.billing_period_end).label("period_end"),
                func.sum(RawBillingLine.billed_cost).label("total_billed"),
                func.count(RawBillingLine.id).label("line_count"),
            )
            .group_by(RawBillingLine.invoice_id)
            .all()
        )

        # Batch load attribution data — sum billed_cost where tags contain a team
        # This replaces the N+1 per-invoice subquery
        all_lines = session.query(
            RawBillingLine.invoice_id,
            RawBillingLine.billed_cost,
            RawBillingLine.tags,
        ).all()

        # Pre-compute attributed cost per invoice
        invoice_attribution = {}
        for line in all_lines:
            iid = line.invoice_id
            if iid not in invoice_attribution:
                invoice_attribution[iid] = Decimal("0")
            tags = line.tags
            if isinstance(tags, str):
                import json as _json
                try:
                    tags = _json.loads(tags)
                except (ValueError, TypeError):
                    tags = {}
            if isinstance(tags, dict) and tags.get("team"):
                invoice_attribution[iid] += Decimal(str(line.billed_cost or 0))

        count = 0
        for row in results:
            if not row.period_start:
                continue
            attributed = invoice_attribution.get(row.invoice_id, Decimal("0"))

            total = Decimal(str(row.total_billed or 0))
            unattributed = total - attributed
            coverage = round(attributed / total * 100, 2) if total > 0 else Decimal("0")

            existing = session.query(Invoice).filter_by(invoice_id=row.invoice_id).first()
            if existing:
                existing.total_billed_cost = row.total_billed
                existing.total_line_items = row.line_count
                existing.attributed_cost = attributed
                existing.unattributed_cost = unattributed
                existing.attribution_coverage_pct = coverage
                existing.updated_at = func.now()
            else:
                invoice = Invoice(
                    invoice_id=row.invoice_id,
                    billing_period_start=row.period_start,
                    billing_period_end=row.period_end,
                    total_billed_cost=row.total_billed,
                    total_line_items=row.line_count,
                    attributed_cost=attributed,
                    unattributed_cost=unattributed,
                    attribution_coverage_pct=coverage,
                    status="provisional",
                )
                session.add(invoice)
            count += 1

    logger.info("Normalized %d invoices.", count)
    return count


def normalize_resources(
    terraform_state_path: Optional[str] = None,
    terraform_state_paths: Optional[list] = None,
    arm_template_path: Optional[str] = None,
    cloudformation_path: Optional[str] = None,
    pulumi_state_path: Optional[str] = None,
):
    """Create one resource row per unique resource_id per billing period.

    Supports multiple IaC sources: Terraform, ARM, CloudFormation, Pulumi.
    Each resource is tagged with its IaC source for audit trail.
    """
    # Unified IaC map: resource_id -> {module, resource_type, resource_name}
    # Plus iac_source_map to track which tool manages each resource
    tf_map = {}
    iac_source_map = {}  # resource_id -> iac_source string

    # Terraform (support multiple state files)
    tf_paths = []
    if terraform_state_paths:
        tf_paths.extend(terraform_state_paths)
    elif terraform_state_path:
        tf_paths.append(terraform_state_path)

    for tf_path in tf_paths:
        try:
            single_map = parse_terraform_state(tf_path)
            tf_map.update(single_map)
            for rid in single_map:
                iac_source_map[rid] = "terraform"
            logger.info("Loaded %d terraform identifiers from %s", len(single_map), tf_path)
        except Exception as e:
            logger.warning("Failed to parse terraform state %s: %s", tf_path, e)

    # ARM template
    if arm_template_path:
        from cloudledger.arm import parse_arm_template
        arm_map = parse_arm_template(arm_template_path)
        tf_map.update(arm_map)
        for rid in arm_map:
            iac_source_map[rid] = "arm"
        logger.info("Merged %d ARM-template resource identifiers.", len(arm_map))

    # CloudFormation
    if cloudformation_path:
        from cloudledger.cloudformation import parse_cloudformation_template
        cfn_map = parse_cloudformation_template(cloudformation_path)
        tf_map.update(cfn_map)
        for rid in cfn_map:
            iac_source_map[rid] = "cloudformation"
        logger.info("Merged %d CloudFormation resource identifiers.", len(cfn_map))

    # Pulumi
    if pulumi_state_path:
        from cloudledger.pulumi import parse_pulumi_state
        pulumi_map = parse_pulumi_state(pulumi_state_path)
        tf_map.update(pulumi_map)
        for rid in pulumi_map:
            iac_source_map[rid] = "pulumi"
        logger.info("Merged %d Pulumi resource identifiers.", len(pulumi_map))

    with get_db() as session:
        results = (
            session.query(
                RawBillingLine.resource_id,
                RawBillingLine.resource_name,
                RawBillingLine.service_name,
                RawBillingLine.service_category,
                RawBillingLine.region,
                RawBillingLine.billing_period_start,
                func.sum(RawBillingLine.billed_cost).label("total_cost"),
            )
            .group_by(
                RawBillingLine.resource_id,
                RawBillingLine.resource_name,
                RawBillingLine.service_name,
                RawBillingLine.service_category,
                RawBillingLine.region,
                RawBillingLine.billing_period_start,
            )
            .all()
        )

        # Build a lookup for tags by resource_id + billing_period
        tags_lookup = {}
        for line in session.query(
            RawBillingLine.resource_id,
            RawBillingLine.billing_period_start,
            RawBillingLine.tags,
        ).filter(RawBillingLine.tags.isnot(None)).all():
            tags_lookup[(line.resource_id, line.billing_period_start)] = line.tags

        count = 0
        for row in results:
            rid = row.resource_id
            if not rid:
                continue
            # Check IaC state (terraform, arm, cloudformation, pulumi)
            in_tf = False
            tf_module = None
            iac_source = "none"
            if rid and rid in tf_map:
                in_tf = True
                tf_module = tf_map[rid].get("module")
                iac_source = iac_source_map.get(rid, "terraform")
            # Also check by ARN if the short id didn't match
            if not in_tf and rid:
                for tf_key, tf_meta in tf_map.items():
                    if rid in tf_key or tf_key in rid:
                        in_tf = True
                        tf_module = tf_meta.get("module")
                        iac_source = iac_source_map.get(tf_key, "terraform")
                        break

            # Extract team/cost_center from tags
            tags = tags_lookup.get((rid, row.billing_period_start)) or {}
            if isinstance(tags, str):
                import json
                try:
                    tags = json.loads(tags)
                except (json.JSONDecodeError, ValueError):
                    tags = {}
            team = tags.get("team") if isinstance(tags, dict) else None
            cost_center = tags.get("cost_center") if isinstance(tags, dict) else None
            environment = _derive_environment(row.resource_name, tags, tf_module)

            existing = (
                session.query(Resource)
                .filter_by(resource_id=rid, billing_period_start=row.billing_period_start)
                .first()
            )

            if existing:
                existing.total_cost = row.total_cost
                existing.in_terraform_state = in_tf
                existing.terraform_module = tf_module
                existing.iac_source = iac_source
                existing.team = team
                existing.cost_center = cost_center
                existing.environment = environment
            else:
                resource = Resource(
                    resource_id=rid,
                    resource_name=row.resource_name,
                    service_name=row.service_name,
                    service_category=row.service_category,
                    region=row.region,
                    team=team,
                    cost_center=cost_center,
                    in_terraform_state=in_tf,
                    terraform_module=tf_module,
                    iac_source=iac_source,
                    environment=environment,
                    billing_period_start=row.billing_period_start,
                    total_cost=row.total_cost,
                )
                session.add(resource)
            count += 1

    logger.info("Normalized %d resource records.", count)
    return count


def seed_sample_change_events(billing_period_start: date, n: int = 5):
    """Seed DEMO change events for testing only. Guarded by CLOUDLEDGER_DEMO_MODE env var."""
    import os
    if not os.environ.get("CLOUDLEDGER_DEMO_MODE"):
        logger.debug("Skipping seed_sample_change_events (set CLOUDLEDGER_DEMO_MODE=1 to enable demo data)")
        return 0
    with get_db() as session:
        existing = session.query(ChangeEvent).count()
        if existing > 0:
            return 0

        managed = (
            session.query(Resource)
            .filter(
                Resource.billing_period_start == billing_period_start,
                Resource.in_terraform_state == True,
            )
            .limit(n)
            .all()
        )

        count = 0
        for i, r in enumerate(managed):
            ce = ChangeEvent(
                resource_id=r.resource_id,
                event_type="terraform_apply",
                event_date=billing_period_start - timedelta(days=2),
                pr_number=str(100 + i),
                pr_title=f"Scale {r.service_name} capacity",
                pr_author="infra-bot",
                commit_sha=f"abc{i:04d}def",
                terraform_module=r.terraform_module,
                description=f"Planned resize of {r.resource_name or r.resource_id}",
                estimated_cost_delta=Decimal("500.00"),
            )
            session.add(ce)
            count += 1

    if count:
        logger.info("Seeded %d sample change events.", count)
    return count


def build_logical_resources(billing_period: str):
    """Aggregate related billing line items under logical resources.

    Handles EKS clusters (nodes, volumes, ELBs) and RDS clusters (replicas, storage, IO).
    """
    import re
    period_start = date.fromisoformat(f"{billing_period}-01")

    with get_db() as session:
        # Find all resources for this period
        resources = (
            session.query(Resource)
            .filter(Resource.billing_period_start == period_start)
            .all()
        )

        # Build lookup maps
        resource_by_id = {r.resource_id: r for r in resources}

        # Find EKS clusters (in Terraform state with service_name containing EKS)
        eks_clusters = [r for r in resources if r.in_terraform_state and r.service_name and "eks" in r.service_name.lower()]

        # Find RDS clusters
        rds_clusters = [r for r in resources if r.in_terraform_state and r.service_name and ("rds" in r.service_name.lower() or "aurora" in r.service_name.lower())]

        # Clear existing logical resources for this period
        from cloudledger.database import LogicalResource
        session.query(LogicalResource).filter(LogicalResource.billing_period_start == period_start).delete()

        count = 0

        # For each EKS cluster, find related resources by tags or naming
        for cluster in eks_clusters:
            cluster_name = (cluster.resource_name or cluster.resource_id or "").lower()
            cluster_id = cluster.resource_id

            # The cluster itself is a child
            session.add(LogicalResource(
                logical_resource_id=cluster_id,
                logical_resource_name=cluster.resource_name,
                resource_type="eks_cluster",
                child_resource_id=cluster_id,
                relationship="cluster",
                billing_period_start=period_start,
            ))
            count += 1

            # Find EC2 instances, volumes, ELBs that match by cluster name in tags or name
            for r in resources:
                if r.resource_id == cluster_id:
                    continue
                r_name = (r.resource_name or r.resource_id or "").lower()
                r_svc = (r.service_name or "").lower()

                # Match EC2 nodes (same team, name contains cluster name)
                is_match = False
                relationship = "associated"

                if cluster_name and cluster_name in r_name:
                    is_match = True
                    if "ec2" in r_svc or "instance" in r_svc:
                        relationship = "node"
                    elif "ebs" in r_svc or "vol" in r_name:
                        relationship = "volume"
                    elif "elb" in r_svc or "load" in r_svc:
                        relationship = "load_balancer"
                    elif "nat" in r_name:
                        relationship = "nat_gateway"

                if is_match:
                    session.add(LogicalResource(
                        logical_resource_id=cluster_id,
                        logical_resource_name=cluster.resource_name,
                        resource_type="eks_cluster",
                        child_resource_id=r.resource_id,
                        relationship=relationship,
                        billing_period_start=period_start,
                    ))
                    count += 1

        # For each RDS cluster, find replicas and storage
        for cluster in rds_clusters:
            cluster_name = (cluster.resource_name or cluster.resource_id or "").lower()
            cluster_id = cluster.resource_id

            session.add(LogicalResource(
                logical_resource_id=cluster_id,
                logical_resource_name=cluster.resource_name,
                resource_type="rds_cluster",
                child_resource_id=cluster_id,
                relationship="primary",
                billing_period_start=period_start,
            ))
            count += 1

            for r in resources:
                if r.resource_id == cluster_id:
                    continue
                r_name = (r.resource_name or r.resource_id or "").lower()
                r_svc = (r.service_name or "").lower()

                if cluster_name and cluster_name in r_name and ("rds" in r_svc or "aurora" in r_svc):
                    relationship = "replica" if "replica" in r_name or "reader" in r_name else "storage" if "storage" in r_name else "associated"
                    session.add(LogicalResource(
                        logical_resource_id=cluster_id,
                        logical_resource_name=cluster.resource_name,
                        resource_type="rds_cluster",
                        child_resource_id=r.resource_id,
                        relationship=relationship,
                        billing_period_start=period_start,
                    ))
                    count += 1

    logger.info("Built %d logical resource mappings.", count)
    return count


if __name__ == "__main__":
    import sys
    normalize_invoices()
    tf_path = sys.argv[1] if len(sys.argv) > 1 else "data/samples/terraform.tfstate"
    normalize_resources(tf_path)
    seed_sample_change_events(date(2025, 2, 1))
