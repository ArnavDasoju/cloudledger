-- Staging model: clean and type-cast raw billing lines, filter out credits
-- Business context: Transforms raw FOCUS 1.2 CSV data into a consistent
-- typed format. Credits are excluded because they are handled separately
-- in the reconciliation process.
select
    id,
    invoice_id,
    billing_period_start,
    billing_period_end,
    charge_period_start,
    charge_period_end,
    service_name,
    service_category,
    resource_id,
    resource_name,
    region,
    availability_zone,
    charge_type,
    description,
    cast(quantity as numeric(18, 6)) as quantity,
    unit,
    cast(unit_price as numeric(18, 10)) as unit_price,
    cast(billed_cost as numeric(18, 6)) as billed_cost,
    cast(list_cost as numeric(18, 6)) as list_cost,
    cast(effective_cost as numeric(18, 6)) as effective_cost,
    tags,
    provider,
    loaded_at,
    case
        when charge_type = 'Credit' then true
        else false
    end as is_credit,
    case
        when charge_type = 'Usage' then true
        else false
    end as is_usage
from {{ source('cloudledger', 'raw_billing_lines') }}
where charge_type != 'Credit'
