"""Generate a realistic terraform.tfstate JSON covering ~70% of sample resources."""

import json
import os
import random

random.seed(42)

MODULES = [
    "module.platform",
    "module.platform.module.vpc",
    "module.platform.module.eks",
    "module.data",
    "module.data.module.rds",
    "module.data.module.s3",
    "module.api",
    "module.api.module.lambda",
    "module.api.module.cloudfront",
]

TF_RESOURCE_TYPES = {
    "ec2": "aws_instance",
    "rds": "aws_db_instance",
    "s3": "aws_s3_bucket",
    "lambda": "aws_lambda_function",
    "cloudfront": "aws_cloudfront_distribution",
    "eks": "aws_eks_cluster",
}


def _detect_service(resource_id: str) -> str:
    for key in TF_RESOURCE_TYPES:
        if f":{key}:" in resource_id or f"aws:{key}" in resource_id:
            return key
    if ":s3:::" in resource_id:
        return "s3"
    return "ec2"


def main():
    samples_dir = os.path.join(os.path.dirname(__file__), "samples")

    # Use month2 resource IDs if available (terraform state validates against current period)
    m2_file = os.path.join(samples_dir, "_month2_resource_ids.txt")
    id_file = m2_file if os.path.exists(m2_file) else os.path.join(samples_dir, "_resource_ids.txt")

    if not os.path.exists(id_file):
        print("Run generate_sample_data.py first to create resource ID files")
        return

    with open(id_file) as f:
        all_ids = [line.strip() for line in f if line.strip()]

    # Pick ~70% of month2 resources to be in terraform state
    # The remaining 30% (~15 resources) will show as drift
    n_managed = int(len(all_ids) * 0.70)
    managed_ids = random.sample(all_ids, n_managed)

    resources = []
    for rid in managed_ids:
        svc = _detect_service(rid)
        tf_type = TF_RESOURCE_TYPES.get(svc, "aws_instance")
        module = random.choice(MODULES)
        short_name = rid.split("/")[-1] if "/" in rid else rid.split(":")[-1]

        resources.append({
            "module": module,
            "mode": "managed",
            "type": tf_type,
            "name": short_name.replace("-", "_"),
            "provider": "provider[\"registry.terraform.io/hashicorp/aws\"]",
            "instances": [
                {
                    "schema_version": 1,
                    "attributes": {
                        "id": short_name,
                        "arn": rid,
                        "tags": {
                            "ManagedBy": "terraform",
                            "Module": module,
                        },
                    },
                }
            ],
        })

    state = {
        "version": 4,
        "terraform_version": "1.6.6",
        "serial": 42,
        "lineage": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "outputs": {},
        "resources": resources,
    }

    out_path = os.path.join(samples_dir, "terraform.tfstate")
    with open(out_path, "w") as f:
        json.dump(state, f, indent=2)

    print(f"Wrote terraform.tfstate with {len(resources)} managed resources ({len(all_ids)} total)")
    print(f"  → {len(all_ids) - n_managed} resources will show as drift")


if __name__ == "__main__":
    main()
