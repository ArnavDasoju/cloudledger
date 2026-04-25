-- Custom dbt test: if a resource is marked as in_terraform_state in one
-- period, it should be in_terraform_state in adjacent periods too
-- (unless it was newly created or removed). Inconsistency here indicates
-- a terraform state parsing issue between pipeline runs.

with tf_status_changes as (
    select
        r1.resource_id,
        r1.billing_period_start as period_1,
        r2.billing_period_start as period_2,
        r1.in_terraform_state as tf_period_1,
        r2.in_terraform_state as tf_period_2
    from {{ ref('stg_resources') }} r1
    inner join {{ ref('stg_resources') }} r2
        on r1.resource_id = r2.resource_id
        and r2.billing_period_start > r1.billing_period_start
    where r1.in_terraform_state != r2.in_terraform_state
)

-- Flag cases where terraform status flipped without a corresponding
-- new_resource or removed_resource variance code
select
    tsc.resource_id,
    tsc.period_1,
    tsc.period_2,
    tsc.tf_period_1,
    tsc.tf_period_2
from tf_status_changes tsc
left join {{ source('cloudledger', 'variance_report') }} vr
    on tsc.resource_id = vr.resource_id
    and vr.current_period_start = tsc.period_2
    and vr.reason_code in ('new_resource', 'removed_resource')
where vr.id is null
