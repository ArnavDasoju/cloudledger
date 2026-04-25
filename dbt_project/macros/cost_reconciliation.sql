-- Macro: reconcile cost totals between two models
-- Usage: {{ cost_reconciliation('model_a', 'model_b', 'join_key', 'cost_col_a', 'cost_col_b', 0.01) }}
-- Returns rows where the cost difference exceeds the tolerance

{% macro cost_reconciliation(model_a, model_b, join_key, cost_col_a, cost_col_b, tolerance=0.01) %}

with source_a as (
    select {{ join_key }}, sum({{ cost_col_a }}) as total_a
    from {{ ref(model_a) }}
    group by {{ join_key }}
),

source_b as (
    select {{ join_key }}, sum({{ cost_col_b }}) as total_b
    from {{ ref(model_b) }}
    group by {{ join_key }}
)

select
    coalesce(a.{{ join_key }}, b.{{ join_key }}) as {{ join_key }},
    coalesce(a.total_a, 0) as total_a,
    coalesce(b.total_b, 0) as total_b,
    abs(coalesce(a.total_a, 0) - coalesce(b.total_b, 0)) as difference
from source_a a
full outer join source_b b on a.{{ join_key }} = b.{{ join_key }}
where abs(coalesce(a.total_a, 0) - coalesce(b.total_b, 0)) > {{ tolerance }}

{% endmacro %}
