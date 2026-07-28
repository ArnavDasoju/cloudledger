# Variance Engine

## How CloudLedger computes variance

CloudLedger compares cloud costs between two billing periods at the resource level. For every resource that appears in either the prior or current month, the engine computes a dollar delta, a percentage delta, and assigns a reason code explaining why the cost changed.

The engine operates on the `resources` table, which contains one row per unique `resource_id` per billing period. Each resource already has its total cost aggregated from raw billing lines, and its IaC status resolved from uploaded Terraform, ARM, CloudFormation, or Pulumi state files.

The output is one `variance_report` row per resource, containing the prior cost, current cost, delta, reason code, confidence score, human-readable evidence string, and a structured evidence chain JSON for audit.

**Source:** `cloudledger/variance.py:160-497` (compute_variance function), `backend/server.py:175-198` (pipeline/run endpoint that calls it)


## What is day normalization and why does it matter?

Different months have different numbers of days. February has 28 (or 29), March has 31. A resource that costs exactly $100/day would show $2,800 in February and $3,100 in March — a $300 "increase" that is not a real change.

CloudLedger adjusts for this by computing a day ratio:

```
day_ratio = current_month_days / prior_month_days
prior_cost_normalized = prior_cost_raw * day_ratio
```

For example, comparing February (28 days) to March (31 days): `day_ratio = 31/28 = 1.107`. A $2,800 February cost normalizes to $3,100, so the adjusted delta is $0 — correctly classified as steady state rather than a cost increase.

Two deltas are computed for each resource:

- **Raw delta** (`current_cost - prior_cost_raw`): What appears on the actual invoices. This is stored on the variance row and shown to users.
- **Normalized delta** (`current_cost - prior_cost_normalized`): The real change after adjusting for month length. This drives the classification decision between `steady_state` (within 5%) and `usage_growth` (exceeds 5%).

**Source:** `cloudledger/variance.py:289-293` (day_ratio calculation), `cloudledger/variance.py:302-318` (both deltas computed), `cloudledger/variance.py:372-377` (5% threshold applied to normalized delta)


## How does the classification decision tree work?

Every resource is evaluated through a fixed priority chain. The first matching rule wins — once a reason code is assigned, subsequent rules are skipped.

1. **Edge case detection** — Check the resource's charge types and description for known billing patterns (Savings Plans, Reserved Instances, credits, marketplace, spot, data transfer). If matched, the resource gets the corresponding edge-case code and is flagged as `excluded=True`.

2. **New resource** — The resource_id exists in the current period but not the prior period.

3. **Removed resource** — The resource_id exists in the prior period but not the current period.

4. **Planned** — The resource is managed by IaC (`in_terraform_state=True`) AND a matching change event was found within the +/-7 day window around the billing period start.

5. **Drift sub-classification** — The resource is NOT in any IaC state. Sub-classified based on tags and cost signals into one of: `non_terraform_iac`, `orphan_sdk_created`, `legacy_untracked`, or `orphan_unknown`.

6. **Usage growth** — The resource IS in IaC, has no change event, and the day-normalized percentage change exceeds 5%.

7. **Steady state** — The resource IS in IaC, has no change event, and the day-normalized percentage change is 5% or less.

8. **Price change** — Fallback for any resource that did not match the above conditions.

**Source:** `cloudledger/variance.py:339-379`


## What is a confidence score?

Each variance row receives a confidence score between 0 and 1 indicating how reliable the classification is. Higher scores mean more evidence supports the reason code.

| Score | Assigned when |
|-------|--------------|
| 0.95 | Resource is managed by IaC (planned, usage_growth, steady_state) |
| 0.90 | Edge case detected from charge type or description pattern |
| 0.85 | `non_terraform_iac` — tags indicate non-Terraform IaC management |
| 0.70 | `orphan_sdk_created` — has team tags but no IaC state |
| 0.60 | `legacy_untracked` — low-cost, pre-IaC resource |
| 0.50 | `orphan_unknown` — no tags, no IaC, origin unknown |

The scores are used to compute **attribution coverage**: the percentage of variance rows where `confidence_score >= 0.70`. This metric is reported on the Close Packet and indicates what fraction of your bill change CloudLedger could confidently explain.

```
attribution_coverage_pct = (rows with confidence >= 0.70) / total_rows * 100
```

**Source:** `cloudledger/variance.py:381-397` (score assignment), `cloudledger/variance.py:483-486` (coverage calculation)


## What is an evidence chain?

Every variance row includes two forms of supporting evidence:

**`evidence`** (text) — A human-readable string summarizing the classification. Displayed in the Variance screen's expandable detail panel. Examples:
- "PR #142: Scale EKS capacity; Managed by terraform (modules/eks)"
- "Day-adjusted delta is 2.3% (within normal range for 28 to 31 day month)"
- "New Amazon EC2 resource (team: backend) costing 1,200/mo"
- "Not in any IaC state — possible drift"

**`evidence_chain`** (JSON) — A structured object stored in the database for audit. It records the inputs to the classification and each decision step.

The chain contains:
- `inputs`: resource_id, prior_cost, current_cost, delta_pct, in_iac, iac_source, iac_module, charge_types
- `classification_steps`: an ordered list of steps, each with `step` (name), `result`, and `detail`

For edge-case resources, the chain has one step: `edge_case_detection`. For new/removed resources, one step: `period_presence`. For all other resources, up to three steps: `iac_lookup` (managed or unmanaged), `change_event_match` (matched or no_match), and `classification` (final reason code with delta and IaC context).

**Source:** `cloudledger/variance.py:71-157` (chain builder), `cloudledger/variance.py:399-435` (evidence string and chain invocation), `cloudledger/database.py:159-160` (evidence and evidence_chain columns)


## What are the baseline modes?

The variance engine supports three ways to determine the "prior" cost for comparison:

**prior_month** (default) — Compares the current period to the immediately preceding period. This is what the UI pipeline uses.

**rolling_3m** — Averages costs from the three months before the current period. If a resource does not appear in all three months, only the months where it existed are averaged. This smooths out one-time spikes and produces a more stable baseline. Internally, the engine creates synthetic resource objects with the averaged cost.

**same_month_last_year** — Compares to the same calendar month in the prior year (e.g. March 2025 vs March 2024). Useful for seasonal businesses where month-over-month comparison is misleading.

The baseline mode is a parameter on the `compute_variance()` function. The UI pipeline always uses `prior_month`. The other two modes are available programmatically but not exposed in the frontend.

**Source:** `cloudledger/variance.py:160-229`


## What is the change event window?

To classify a cost change as `planned`, the engine needs a matching infrastructure change event (a merged PR, a terraform apply, etc.) near the billing period.

The engine loads all `change_events` rows with an `event_date` within **7 days before** or **7 days after** the billing period start date.

Change events also support short-ID matching: if the change event's `resource_id` contains a `/` or `:`, the engine extracts the last segment and adds it as an additional lookup key. This handles cases where a GitHub PR references a Terraform module path but the billing resource has a full ARN.

**Source:** `cloudledger/variance.py:254-279`


## How are the four root-cause buckets defined?

The Root Causes screen and the Close Packet group the 16 reason codes into four high-level buckets:

| Bucket | Reason codes included |
|--------|----------------------|
| **Planned** | `planned` |
| **Drift** | `orphan_sdk_created`, `orphan_unknown`, `legacy_untracked`, `non_terraform_iac` |
| **Usage** | `usage_growth`, `new_resource`, `removed_resource`, `price_change`, `steady_state` |
| **Edge Cases** | `savings_plan_allocation`, `ri_coverage_shift`, `cross_service_transfer`, `marketplace_subscription`, `spot_price_volatility`, `credit_applied` |

Any reason code not in the above sets falls into the Drift bucket as a default.

Note: the bare string `drift` appears in the `DRIFT_CODES` set used for bucketing, but it is never assigned as a reason code by the variance engine. It exists only as a grouping label in the frontend.

**Source:** `backend/server.py:72-78` (set definitions), `backend/server.py:484-508` (bucketing logic in root_causes endpoint)


---

## Reason Code Reference

### Why is my resource marked as "planned"?

The resource is managed by Infrastructure-as-Code (its `in_terraform_state` flag is true), AND a matching change event was found within 7 days of the billing period start. This typically means someone merged a PR that modified a `.tf` file affecting this resource, or ran a `terraform apply`.

The evidence string includes the PR number and title when available (e.g. "PR #142: Scale EKS capacity").

- **Conditions:** `in_terraform_state == True` AND `resource_id` found in change event window
- **Confidence:** 0.95
- **Bucket:** Planned
- **Source:** `cloudledger/variance.py:346-347`, `cloudledger/variance.py:403-406`


### Why is my resource marked as "new_resource"?

The resource appears in the current billing period but has no matching `resource_id` in the prior period. It was newly provisioned during this month. The entire current-month cost is the variance delta.

The evidence string includes the service type, team tag (if present), and monthly cost.

- **Conditions:** `resource_id` not in prior period resources
- **Confidence:** depends on IaC and tag status (0.95 if IaC-managed, 0.50-0.70 otherwise)
- **Bucket:** Usage
- **Source:** `cloudledger/variance.py:342-343`, `cloudledger/variance.py:411-414`


### Why is my resource marked as "removed_resource"?

The resource existed in the prior billing period but is absent from the current period. It was deprovisioned, deleted, or stopped generating charges. The prior-month cost appears as a negative delta.

- **Conditions:** `resource_id` not in current period resources
- **Confidence:** depends on IaC and tag status
- **Bucket:** Usage
- **Source:** `cloudledger/variance.py:344-345`


### Why is my resource marked as "usage_growth"?

The resource IS managed by IaC, has no matching change events in the window, but its cost changed by more than 5% after adjusting for month length. This indicates organic growth — more API calls, more storage consumed, more compute hours — rather than an infrastructure change.

The 5% threshold uses the day-normalized percentage, not the raw percentage. A resource going from $2,800 (February, 28 days) to $3,200 (March, 31 days) has a raw delta of +14.3% but a normalized delta of only +3.2%, so it would be `steady_state`, not `usage_growth`.

- **Conditions:** `in_terraform_state == True` AND no change event AND `abs(day_normalized_pct) > 5`
- **Confidence:** 0.95
- **Bucket:** Usage
- **Source:** `cloudledger/variance.py:372-374`, `cloudledger/variance.py:409-410`


### Why is my resource marked as "steady_state"?

The resource is managed by IaC, has no change events, and its day-normalized cost change is 5% or less. After accounting for the different number of days between the two months, the cost did not meaningfully change. No action needed.

The evidence string shows the exact day-adjusted delta (e.g. "Day-adjusted delta is 2.3% (within normal range for 28 to 31 day month)").

- **Conditions:** `in_terraform_state == True` AND no change event AND `abs(day_normalized_pct) <= 5`
- **Confidence:** 0.95
- **Bucket:** Usage
- **Source:** `cloudledger/variance.py:375-377`, `cloudledger/variance.py:407-408`


### Why is my resource marked as "price_change"?

This is the fallback classification. The resource did not match any prior rule in the decision tree. This typically means the unit price changed due to a provider pricing update, a commitment tier expiration, or a rate adjustment that does not correspond to a Savings Plan or RI charge type.

In practice this code is rarely assigned because the decision tree above it is comprehensive.

- **Conditions:** none of the preceding conditions were true
- **Confidence:** 0.50 (default)
- **Bucket:** Usage
- **Source:** `cloudledger/variance.py:378-379`


### Why is my resource marked as "orphan_sdk_created"?

The resource is NOT in any uploaded IaC state file, BUT it has a `team` tag in its billing data. This combination suggests it was created manually — via the AWS Console, Azure Portal, CLI, or SDK — by someone on a known team, outside of infrastructure code.

- **Conditions:** `in_terraform_state == False` AND resource has a team tag AND no non-Terraform IaC tags detected
- **Confidence:** 0.70
- **Bucket:** Drift
- **Source:** `cloudledger/variance.py:366-367`


### Why is my resource marked as "orphan_unknown"?

The resource is NOT in any IaC state AND has no team tags. CloudLedger cannot determine who created it or why. It may be a leftover from a deleted project, a resource created by a third-party tool, or something provisioned manually without following tagging conventions.

This is the lowest-confidence classification. These resources are typically the highest priority for investigation.

- **Conditions:** `in_terraform_state == False` AND no team tag AND not detected as non-Terraform IaC AND does not qualify as `legacy_untracked`
- **Confidence:** 0.50
- **Bucket:** Drift
- **Source:** `cloudledger/variance.py:370-371`


### Why is my resource marked as "legacy_untracked"?

The resource is NOT in any IaC state, has no team tags, BUT it existed in the prior period (it is not new) and its current cost is below $200/month. This pattern typically indicates a small, long-running resource that predates the organization's adoption of Terraform — a legacy resource that was never imported.

- **Conditions:** `in_terraform_state == False` AND no team tag AND `prior_cost > 0` AND `current_cost < 200`
- **Confidence:** 0.60
- **Bucket:** Drift
- **Source:** `cloudledger/variance.py:368-369`


### Why is my resource marked as "non_terraform_iac"?

The resource is NOT in the uploaded Terraform state, BUT its billing tags indicate it is managed by a different IaC tool. The engine checks for these tag keys and values:

- Tags `managed_by`, `managed-by`, `iac_tool`, or `CreatedBy` with a value of `cloudformation`, `cdk`, `pulumi`, or `serverless`
- Presence of the AWS-managed tag `aws:cloudformation:stack-name`

If any match, the resource is classified as managed by non-Terraform IaC rather than as drift. This prevents false drift alerts for organizations that use multiple IaC tools.

- **Conditions:** `in_terraform_state == False` AND IaC management tags detected
- **Confidence:** 0.85
- **Bucket:** Drift
- **Source:** `cloudledger/variance.py:354-365`


### Why is my resource marked as "savings_plan_allocation"?

The resource's billing lines include one of these AWS charge types: `SavingsPlanCoveredUsage`, `SavingsPlanNegation`, `SavingsPlanRecurringFee`, or `SavingsPlanUpfrontFee`. Cost movement here is due to Savings Plan coverage being allocated or reallocated across resources, not due to actual usage or infrastructure changes.

Resources with this code are marked `excluded=True` and grouped into the Edge Cases bucket.

- **Conditions:** charge_type matches one of the four Savings Plan patterns
- **Confidence:** 0.90
- **Bucket:** Edge Cases
- **Source:** `cloudledger/variance.py:29-32` (charge type map), `cloudledger/variance.py:49-51` (detection)


### Why is my resource marked as "ri_coverage_shift"?

The resource's billing lines include the charge type `RIFee` or `DiscountedUsage`. Reserved Instance coverage shifted between resources, changing how costs are allocated. The underlying usage may not have changed at all.

- **Conditions:** charge_type is `RIFee` or `DiscountedUsage`
- **Confidence:** 0.90
- **Bucket:** Edge Cases
- **Source:** `cloudledger/variance.py:33-34`


### Why is my resource marked as "credit_applied"?

The resource's billing lines include charge type `Credit`, `Refund`, or `BundledDiscount`. A credit, refund, or bundled discount was applied to this resource, creating a negative cost delta that does not reflect a real infrastructure or usage change.

- **Conditions:** charge_type is `Credit`, `Refund`, or `BundledDiscount`
- **Confidence:** 0.90
- **Bucket:** Edge Cases
- **Source:** `cloudledger/variance.py:35-37`


### Why is my resource marked as "marketplace_subscription"?

The resource's description contains keywords indicating an AWS or Azure Marketplace subscription: `marketplace`, `mp-`, or `aws marketplace` (case-insensitive). These are third-party software costs billed through the cloud provider. Cost changes are driven by vendor pricing or subscription adjustments, not by your infrastructure decisions.

- **Conditions:** resource description (lowercased) contains a marketplace indicator keyword
- **Confidence:** 0.90
- **Bucket:** Edge Cases
- **Source:** `cloudledger/variance.py:40` (indicator list), `cloudledger/variance.py:53-55` (detection)


### Why is my resource marked as "spot_price_volatility"?

The resource's description or charge type contains keywords indicating spot instance usage: `spot` or `spotusage` (case-insensitive). Spot instance pricing fluctuates based on real-time market demand for spare compute capacity, so cost variance is expected and generally not actionable.

- **Conditions:** resource description or charge_type contains a spot indicator keyword
- **Confidence:** 0.90
- **Bucket:** Edge Cases
- **Source:** `cloudledger/variance.py:41` (indicator list), `cloudledger/variance.py:57-62` (detection)


### Why is my resource marked as "cross_service_transfer"?

The resource's description contains keywords indicating data transfer costs: `datatransfer`, `data transfer`, `cloudfront`, or `nat gateway` (case-insensitive). These are cross-service or cross-region network transfer charges that often appear as separate billing line items and fluctuate independently of the resources that generate the traffic.

- **Conditions:** resource description (lowercased) contains a data transfer indicator keyword
- **Confidence:** 0.90
- **Bucket:** Edge Cases
- **Source:** `cloudledger/variance.py:42` (indicator list), `cloudledger/variance.py:64-66` (detection)
