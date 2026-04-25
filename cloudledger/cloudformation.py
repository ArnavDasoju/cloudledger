"""Parses CloudFormation template JSON to extract resource mappings."""

import json
from typing import Dict


def parse_cloudformation_template(filepath: str) -> Dict[str, dict]:
    """Parse a CloudFormation template and return resource_id -> metadata mapping."""
    with open(filepath) as f:
        template = json.load(f)

    resource_map = {}
    for logical_id, resource in template.get("Resources", {}).items():
        rtype = resource.get("Type", "unknown")
        props = resource.get("Properties", {})
        name = props.get("Name") or props.get("FunctionName") or props.get("BucketName") or logical_id
        resource_map[logical_id] = {
            "module": "cloudformation",
            "resource_type": rtype,
            "resource_name": name,
        }

    return resource_map
