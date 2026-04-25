-- Staging model: clean resource records with terraform flag and management status
-- Business context: one row per unique cloud resource per billing period,
-- enriched with IaC metadata to distinguish managed vs unmanaged spend.

select
    id,
    resource_id,
    coalesce(resource_name, resource_id) as resource_name,
    service_name,
    coalesce(service_category, 'Uncategorized') as service_category,
    coalesce(region, 'unknown') as region,
    coalesce(provider, 'AWS') as provider,
    coalesce(team, 'Unattributed') as team,
    coalesce(cost_center, 'UNALLOCATED') as cost_center,
    in_terraform_state,
    terraform_module,
    cloudtrail_owner,
    billing_period_start,
    cast(total_cost as numeric(18, 2)) as total_cost,
    -- Management status derived from terraform and ownership data
    case
        when in_terraform_state = true then 'managed'
        when team is not null and team != '' then 'tagged_only'
        else 'unmanaged'
    end as management_status
from {{ source('cloudledger', 'resources') }}
where resource_id is not null
