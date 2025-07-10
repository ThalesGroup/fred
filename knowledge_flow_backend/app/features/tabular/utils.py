from app.features.tabular.structures import SQLQueryPlan

def column_name_corrector(col: str) -> str:
    if any(c in col for c in ' ()'):
        return f'"{col}"'
    return col

def plan_to_sql(plan: SQLQueryPlan) -> str:
    parts = []

    # SELECT clause
    select_clauses = []
    if plan.aggregations:
        for agg in plan.aggregations:
            alias = f" AS {agg.alias}" if agg.alias else ""
            distinct_keyword = "DISTINCT " if getattr(agg, "distinct", False) else ""
            select_clauses.append(
                f"{agg.function.upper()}({distinct_keyword}{column_name_corrector(agg.column)}){alias}"
            )

    if plan.columns:
        select_clauses.extend([column_name_corrector(c) for c in plan.columns])

    if not select_clauses:
        select_clauses.append("*")

    parts.append("SELECT " + ", ".join(select_clauses))

    # FROM clause
    parts.append(f"FROM {column_name_corrector(plan.table)}")

    # JOINS
    if plan.joins:
        for join in plan.joins:
            join_type = join.type.upper() if join.type else "INNER"
            parts.append(
                f"{join_type} JOIN {column_name_corrector(join.table)} ON {join.on}"
            )

    # WHERE
    conditions = []
    if plan.filters:
        for filt in plan.filters:
            col_sql = column_name_corrector(filt.column)
            op_sql = filt.op.upper()
            val = filt.value

            if isinstance(val, str):
                val_str = f"'{val}'"
            elif isinstance(val, list):
                val_list = ", ".join(f"'{v}'" if isinstance(v, str) else str(v) for v in val)
                val_str = f"({val_list})"
            else:
                val_str = str(val)

            if op_sql == "IN":
                condition = f"{col_sql} IN {val_str}"
            else:
                condition = f"{col_sql} {op_sql} {val_str}"

            conditions.append(condition)

    if conditions:
        parts.append("WHERE " + " AND ".join(conditions))


    # GROUP BY
    if plan.group_by:
        parts.append("GROUP BY " + ", ".join(column_name_corrector(c) for c in plan.group_by))

    # ORDER BY
    if plan.order_by:
        order_clauses = []
        for ob in plan.order_by:
            direction = ob.direction.upper() if ob.direction else "ASC"
            order_clauses.append(f"{column_name_corrector(ob.column)} {direction}")
        parts.append("ORDER BY " + ", ".join(order_clauses))

    # LIMIT
    if plan.limit is not None:
        parts.append(f"LIMIT {plan.limit}")

    # Combine all
    return " ".join(parts)
