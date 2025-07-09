from app.features.tabular.structures import SQLQueryPlan

def plan_to_sql(plan: SQLQueryPlan) -> str:
    parts = []

    # SELECT clause
    select_clauses = []
    if plan.aggregations:
        for agg in plan.aggregations:
            alias = f" AS {agg.alias}" if agg.alias else ""
            select_clauses.append(f"{agg.function.upper()}({agg.column}){alias}")

    if plan.columns:
        select_clauses.extend(plan.columns)

    if not select_clauses:
        select_clauses.append("*")

    parts.append("SELECT " + ", ".join(select_clauses))

    # FROM clause
    parts.append(f"FROM {plan.table}")

    # JOINS
    if plan.joins:
        for join in plan.joins:
            join_type = join.type.upper() if join.type else "INNER"
            parts.append(f"{join_type} JOIN {join.table} ON {join.on}")

    # WHERE
    if plan.filters:
        conditions = []
        for col, val in plan.filters.items():
            if isinstance(val, str):
                val_str = f"'{val}'"
            else:
                val_str = str(val)
            conditions.append(f"{col} = {val_str}")
        if conditions:
            parts.append("WHERE " + " AND ".join(conditions))

    # GROUP BY
    if plan.group_by:
        parts.append("GROUP BY " + ", ".join(plan.group_by))

    # ORDER BY
    if plan.order_by:
        parts.append("ORDER BY " + ", ".join(plan.order_by))

    # LIMIT
    if plan.limit is not None:
        parts.append(f"LIMIT {plan.limit}")

    # Combine all
    return " ".join(parts)