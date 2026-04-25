-- Custom dbt test: verify that each invoice total matches
-- the sum of its billing lines within a $0.01 tolerance.
-- A failure here indicates a reconciliation issue in the pipeline.

with invoice_totals as (
    select
        invoice_id,
        total_billed_cost
    from {{ ref('int_invoice_totals') }}
),

line_sums as (
    select
        invoice_id,
        sum(billed_cost) as line_total
    from {{ ref('stg_billing_lines') }}
    group by invoice_id
)

-- Return rows that violate the constraint (dbt expects 0 rows for pass)
select
    it.invoice_id,
    it.total_billed_cost,
    ls.line_total,
    abs(it.total_billed_cost - ls.line_total) as difference
from invoice_totals it
inner join line_sums ls on it.invoice_id = ls.invoice_id
where abs(it.total_billed_cost - ls.line_total) > 0.01
