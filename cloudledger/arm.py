"""Parses ARM template JSON to extract resource mappings."""

import json
from typing import Dict


def parse_arm_template(filepath: str) -> Dict[str, dict]:
    """Parse an ARM template and return resource_id -> metadata mapping."""
    with open(filepath) as f:
        template = json.load(f)

    resource_map = {}
    for resource in template.get("resources", []):
        rid = resource.get("id") or resource.get("name", "")
        rtype = resource.get("type", "unknown")
        name = resource.get("name", "unknown")
        resource_map[rid] = {
            "module": rtype,
            "resource_type": rtype,
            "resource_name": name,
        }
        # Also map by name for fuzzy matching
        if name and name != rid:
            resource_map[name] = resource_map[rid]

    return resource_map
