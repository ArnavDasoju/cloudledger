"""Parses terraform.tfstate JSON to extract resource mappings."""

import json
from typing import Dict


def parse_terraform_state(filepath: str) -> Dict[str, dict]:
    """Parse a terraform.tfstate file and return a mapping of resource_id/arn → metadata.

    Returns:
        dict mapping resource_id/arn → {module, resource_type, resource_name}
    """
    with open(filepath) as f:
        state = json.load(f)

    resource_map = {}

    for resource_block in state.get("resources", []):
        module = resource_block.get("module", "root")
        resource_type = resource_block.get("type", "unknown")
        resource_name = resource_block.get("name", "unknown")

        for instance in resource_block.get("instances", []):
            attrs = instance.get("attributes", {})

            # Collect all identifiers: id, arn, and any field containing "resource_id"
            identifiers = set()
            for key in ("id", "arn"):
                val = attrs.get(key)
                if val:
                    identifiers.add(val)
            for key, val in attrs.items():
                if "resource_id" in key and isinstance(val, str) and val:
                    identifiers.add(val)

            meta = {
                "module": module,
                "resource_type": resource_type,
                "resource_name": resource_name,
            }

            for ident in identifiers:
                resource_map[ident] = meta

    return resource_map


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/samples/terraform.tfstate"
    mapping = parse_terraform_state(path)
    print(f"Parsed {len(mapping)} resource identifiers from terraform state")
    for rid, meta in list(mapping.items())[:5]:
        print(f"  {rid[:60]}... → {meta['module']}")
