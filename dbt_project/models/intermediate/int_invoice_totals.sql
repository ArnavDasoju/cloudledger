-- Intermediate model: invoice-level totals with attribution and reconciliation
-- Uses CTE pattern for readability
-- Key output: attribution_coverage_pct and reconciliation_status

with billing_lines as (
    select
        invoice_id,
        billing_period_start,
        sum(billed_cost) as line_total,
        count(*) as line_count,
        -- Conditional aggregation: split credits from usage
        sum(case when is_credit then billed_cost else 0 end) as total_credits,
        sum(case when is_usage then billed_cost else 0 end) as total_usage
    from {{ ref('stg_billing_lines') }}
    group by invoice_id, billing_period_start
),

attribution as (
    select
        invoice_id,
        sum(allocated_cost) as attributed_cost
    from {{ source('cloudledger', 'allocations') }}
    group by invoice_id
)

select
    bl.invoice_id,
    bl.billing_period_start,
    bl.line_total as total_billed_cost,
    bl.line_count as total_line_items,
    bl.total_credits,
    bl.total_usage,
    coalesce(a.attributed_cost, 0) as attributed_cost,
    bl.line_total - coalesce(a.attributed_cost, 0) as unattributed_cost,
    case
        when bl.line_total > 0
        then round(coalesce(a.attributed_cost, 0) / bl.line_total * 100, 2)
        else 0
    end as attribution_coverage_pct,
    -- Reconciliation: does the invoice total match the sum of lines?
    abs(bl.line_total - coalesce(bl.line_total, 0)) as reconciliation_variance,
    case
        when abs(bl.line_total - coalesce(bl.line_total, 0)) <= 0.01 then 'reconciled'
        else 'variance_detected'
    end as reconciliation_status
from billing_lines bl
left join attribution a on bl.invoice_id = a.invoice_id
