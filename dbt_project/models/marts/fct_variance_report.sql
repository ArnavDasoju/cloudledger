-- Mart model: enriched variance report with delta classification and allocation data
-- Business context: the primary analytical fact table powering executive dashboards.
-- Joins variance_report → resources → allocations for full attribution context.

with allocation_summary as (
    -- Aggregate allocation confidence per resource and period
    select
        resource_id,
        billing_period_start,
        sum(allocated_cost) as total_allocated_cost,
        avg(confidence_score) as avg_allocation_confidence,
        count(*) as allocation_count
    from {{ source('cloudledger', 'allocations') }}
    group by resource_id, billing_period_start
),

-- Conditional aggregation: summarize variance by reason code for context
reason_code_totals as (
    select
        current_period_start,
        sum(case when reason_code = 'drift' then delta_dollars else 0 end) as total_drift_delta,
        sum(case when reason_code = 'planned' then delta_dollars else 0 end) as total_planned_delta,
        sum(case when reason_code = 'new_resource' then delta_dollars else 0 end) as total_new_delta,
        sum(case when reason_code = 'removed_resource' then delta_dollars else 0 end) as total_removed_delta,
        sum(case when reason_code = 'usage_growth' then delta_dollars else 0 end) as total_usage_growth_delta,
        sum(case when reason_code = 'price_change' then delta_dollars else 0 end) as total_price_change_delta,
        sum(delta_dollars) as period_total_delta
    from {{ source('cloudledger', 'variance_report') }}
    group by current_period_start
)

-- Multi-table JOIN: variance_report → resources → allocations
select
    vr.id,
    vr.resource_id,
    vr.resource_name,
    vr.service_name,
    vr.team,
    vr.cost_center,
    vr.prior_period_start,
    vr.current_period_start,
    vr.prior_cost,
    vr.current_cost,
    vr.delta_dollars,
    vr.delta_pct,
    vr.reason_code,
    vr.confidence_score,
    vr.evidence,
    vr.pr_number,
    vr.pr_author,
    vr.in_terraform_state,
    vr.reviewed,
    -- Resource enrichment
    r.service_category,
    r.region,
    r.terraform_module,
    -- Allocation enrichment
    coalesce(a.total_allocated_cost, 0) as allocated_cost,
    a.avg_allocation_confidence,
    a.allocation_count,
    -- Delta bucket classification for dashboard filtering
    case
        when abs(vr.delta_pct) > 20 then 'large'
        when abs(vr.delta_pct) > 5 then 'medium'
        else 'small'
    end as delta_bucket,
    -- Human-readable explanation for dashboards
    case vr.reason_code
        when 'planned'          then 'Expected change — matched to a Terraform PR'
        when 'drift'            then 'Unmanaged resource — not in Terraform state'
        when 'new_resource'     then 'New resource appeared this month'
        when 'removed_resource' then 'Resource removed this month'
        when 'usage_growth'     then 'Usage grew — no infrastructure change detected'
        when 'price_change'     then 'Minor cost change — likely a price adjustment'
        else 'Unknown'
    end as reason_description,
    -- Flag high-cost drift for immediate action (drift resources costing over $1000)
    case
        when vr.reason_code = 'drift' and vr.current_cost > 1000 then true
        else false
    end as high_priority_drift,
    -- Period-level context from conditional aggregation CTE
    rct.period_total_delta,
    -- Percentage contribution to total period variance
    case
        when rct.period_total_delta != 0
        then round(vr.delta_dollars / rct.period_total_delta * 100, 2)
        else 0
    end as pct_of_total_variance
from {{ source('cloudledger', 'variance_report') }} vr
left join {{ source('cloudledger', 'resources') }} r
    on vr.resource_id = r.resource_id
    and r.billing_period_start = vr.current_period_start
left join allocation_summary a
    on vr.resource_id = a.resource_id
    and a.billing_period_start = vr.current_period_start
left join reason_code_totals rct
    on vr.current_period_start = rct.current_period_start
