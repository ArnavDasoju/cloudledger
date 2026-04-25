-- Custom dbt test: ensure no resource has a negative total cost
-- after staging transformations. Negative costs should only appear
-- as credits (filtered in staging) — a negative total_cost here
-- indicates a data pipeline issue.

select
    resource_id,
    billing_period_start,
    total_cost
from {{ ref('stg_resources') }}
where total_cost < 0
