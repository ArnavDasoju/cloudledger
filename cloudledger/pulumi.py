"""Parses Pulumi state JSON to extract resource mappings."""

import json
from typing import Dict


def parse_pulumi_state(filepath: str) -> Dict[str, dict]:
    """Parse a Pulumi state file and return resource_id -> metadata mapping."""
    with open(filepath) as f:
        state = json.load(f)

    resource_map = {}
    deployment = state.get("deployment", state)
    for resource in deployment.get("resources", []):
        rtype = resource.get("type", "unknown")
        urn = resource.get("urn", "")
        rid = resource.get("id") or urn
        outputs = resource.get("outputs", {})
        name = outputs.get("name") or resource.get("urn", "").split("::")[-1] if urn else "unknown"

        if rid:
            resource_map[rid] = {
                "module": "pulumi",
                "resource_type": rtype,
                "resource_name": name,
            }
        # Also map by ARN if present
        arn = outputs.get("arn")
        if arn:
            resource_map[arn] = resource_map.get(rid, {
                "module": "pulumi",
                "resource_type": rtype,
                "resource_name": name,
            })

    return resource_map
