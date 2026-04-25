-- Custom dbt test: every resource in the current period should have
-- a corresponding variance report row. Missing rows indicate the
-- variance engine skipped resources during computation.

with current_resources as (
    select distinct resource_id, billing_period_start
    from {{ ref('stg_resources') }}
),

variance_resources as (
    select distinct resource_id, current_period_start
    from {{ source('cloudledger', 'variance_report') }}
)

select
    cr.resource_id,
    cr.billing_period_start
from current_resources cr
left join variance_resources vr
    on cr.resource_id = vr.resource_id
    and cr.billing_period_start = vr.current_period_start
where vr.resource_id is null
    and cr.billing_period_start != (
        select min(billing_period_start) from current_resources
    )
