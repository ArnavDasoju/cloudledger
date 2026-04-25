-- Intermediate model: resource cost by month with window functions
-- Business context: tracks month-over-month spend trends per resource
-- to power variance analysis and anomaly detection.

with resource_months as (
    select
        resource_id,
        resource_name,
        service_name,
        team,
        cost_center,
        in_terraform_state,
        billing_period_start,
        total_cost,

        -- Prior month cost for comparison (window: LAG)
        lag(total_cost) over (
            partition by resource_id
            order by billing_period_start
        ) as prior_month_cost,

        -- Next month cost for forecasting (window: LEAD)
        lead(total_cost) over (
            partition by resource_id
            order by billing_period_start
        ) as next_month_cost,

        -- Rank resources by cost within each service (window: ROW_NUMBER)
        row_number() over (
            partition by service_name, billing_period_start
            order by total_cost desc
        ) as cost_rank_in_service

    from {{ ref('stg_resources') }}
),

-- Calculate month-over-month delta and percentage change
with_deltas as (
    select
        *,
        total_cost - coalesce(prior_month_cost, 0) as mom_delta_dollars,
        case
            when prior_month_cost is not null and prior_month_cost > 0
            then round((total_cost - prior_month_cost) / prior_month_cost * 100, 2)
            else null
        end as mom_delta_pct,

        -- Running average cost over available months
        avg(total_cost) over (
            partition by resource_id
            order by billing_period_start
            rows between 2 preceding and current row
        ) as rolling_3m_avg_cost,

        -- Date grouping for aggregation
        date_trunc('month', billing_period_start) as billing_month

    from resource_months
)

select * from with_deltas
