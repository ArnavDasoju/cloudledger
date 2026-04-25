-- Dimension table: all unique resources with latest metadata
-- Business context: provides the master resource reference for
-- joining into fact tables, with the most recent ownership and cost data.
-- Uses DISTINCT ON to get the latest row per resource_id efficiently.

with latest_resources as (
    -- DISTINCT ON picks the first row per resource_id when ordered by billing_period DESC
    select distinct on (resource_id)
        resource_id,
        resource_name,
        service_name,
        service_category,
        region,
        provider,
        team,
        cost_center,
        in_terraform_state,
        terraform_module,
        cloudtrail_owner,
        total_cost as latest_period_cost,
        billing_period_start as latest_billing_period,
        management_status
    from {{ ref('stg_resources') }}
    order by resource_id, billing_period_start desc
),

-- Conditional aggregation: total drift spend per resource
-- Uses SUM(CASE WHEN ...) for conditional aggregation across periods
drift_summary as (
    select
        resource_id,
        sum(case when not in_terraform_state then total_cost else 0 end) as total_drift_spend,
        sum(case when in_terraform_state then total_cost else 0 end) as total_managed_spend,
        count(distinct billing_period_start) as periods_observed
    from {{ ref('stg_resources') }}
    group by resource_id
)

select
    lr.resource_id,
    lr.resource_name,
    lr.service_name,
    lr.service_category,
    lr.region,
    lr.provider,
    lr.team,
    lr.cost_center,
    lr.in_terraform_state,
    lr.terraform_module,
    lr.cloudtrail_owner,
    lr.latest_period_cost,
    lr.latest_billing_period,
    lr.management_status,
    ds.total_drift_spend,
    ds.total_managed_spend,
    ds.periods_observed
from latest_resources lr
left join drift_summary ds on lr.resource_id = ds.resource_id
