from app.ai.types import Interpretation, SqlPlan


def try_fix_sql(sql: str, error: str, plan: SqlPlan, interpretation: Interpretation) -> str | None:
    fixed = sql.strip().rstrip(";")
    lower_error = error.lower()
    if "does not exist" in lower_error:
        fixed = fixed.replace("amount", "price_order_local")
        fixed = fixed.replace("created_at", "order_timestamp")
        fixed = fixed.replace("id =", "order_id =")
    if "syntax" in lower_error:
        fixed = fixed.replace(";;", ";").rstrip(";")
    if "limit" not in fixed.lower():
        fixed = f"{fixed}\nLIMIT {plan.limit or interpretation.limit or 100}"
    return fixed if fixed != sql.strip().rstrip(";") else None
