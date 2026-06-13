from __future__ import annotations

from typing import Any

import pandas as pd


def run_analysis(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    analysis_kind = plan.get("analysis_kind")
    if analysis_kind == "rank_wip_then_join_production":
        return _rank_wip_then_join_production(plan, runtime_sources)
    if analysis_kind == "detail_rows":
        return _detail_rows(plan, runtime_sources)
    if analysis_kind == "rank_top_n":
        return _rank_top_n(plan, runtime_sources)
    if analysis_kind == "equipment_for_previous_products":
        return _equipment_for_previous_products(plan, runtime_sources)
    if analysis_kind == "aggregate_join":
        return _aggregate_join(plan, runtime_sources)
    if analysis_kind == "production_wip_target_rate":
        return _production_wip_target_rate(plan, runtime_sources)
    if analysis_kind == "lot_count_by_process":
        return _lot_count_by_process(plan, runtime_sources)
    if analysis_kind == "lot_quantity_summary":
        return _lot_quantity_summary(plan, runtime_sources)
    if analysis_kind == "aggregate_wip_total":
        return _aggregate_wip_total(plan, runtime_sources)
    if analysis_kind == "low_output_vs_target":
        return _low_output_vs_target(plan, runtime_sources)
    if analysis_kind == "date_split_production_plan_gap":
        return _date_split_production_plan_gap(plan, runtime_sources)
    if analysis_kind == "overall_production_wip_target":
        return _overall_production_wip_target(plan, runtime_sources)
    if analysis_kind == "equipment_by_model":
        return _equipment_by_model(plan, runtime_sources)
    return _empty_result(plan, f"Unsupported analysis_kind: {analysis_kind}")


def _rank_wip_then_join_production(
    plan: dict[str, Any],
    runtime_sources: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    product_keys = plan["product_grain"]
    rank_step = plan["step_plan"][0]
    wip_df = pd.DataFrame(runtime_sources.get(rank_step["source_alias"], []))
    prod_df = pd.DataFrame(runtime_sources.get("production_today_for_ranked_products", []))

    if wip_df.empty:
        return _empty_result(plan, "No WIP rows found for rank step")

    wip_df["RANK_GROUP"] = wip_df["OPER_NAME"].apply(lambda value: _rank_group_for_process(value, rank_step["rank_groups"]))
    wip_df = wip_df[wip_df["RANK_GROUP"].notna()].copy()
    ranked = _sum_by(wip_df, ["RANK_GROUP", *product_keys], "WIP")
    ranked["WIP_RANK"] = ranked.groupby("RANK_GROUP")["WIP"].rank(method="first", ascending=False).astype(int)
    ranked = ranked[ranked["WIP_RANK"] <= int(rank_step["top_n"])].copy()
    ranked = ranked.sort_values(["RANK_GROUP", "WIP_RANK", "WIP"], ascending=[True, True, False])

    if prod_df.empty:
        production = pd.DataFrame(columns=[*product_keys, "PRODUCTION"])
    else:
        ranked_keys = _key_frame(ranked, product_keys)
        production_source = prod_df.merge(ranked_keys, on=product_keys, how="inner")
        production = _sum_by(production_source, product_keys, "PRODUCTION")

    final = ranked.merge(production, on=product_keys, how="left")
    final["PRODUCTION"] = final["PRODUCTION"].fillna(0).astype(int)
    final = final[["RANK_GROUP", "WIP_RANK", *product_keys, "WIP", "PRODUCTION"]]
    return _result(
        plan,
        final,
        analysis_code=(
            "wip_df -> assign RANK_GROUP -> groupby(RANK_GROUP, product_grain).sum(WIP) -> "
            "rank within each RANK_GROUP -> filter top_n -> production_df filtered by ranked product keys -> "
            "groupby(product_grain).sum(PRODUCTION) -> left join"
        ),
        intermediate_refs={
            "ranked_products": _preview_frame(ranked),
            "production_by_ranked_product": _preview_frame(production),
        },
    )


def _detail_rows(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    step = plan["step_plan"][0]
    rows = runtime_sources.get(step["source_alias"], [])
    frame = pd.DataFrame(rows)
    columns = [column for column in step.get("columns", []) if column in frame.columns]
    if columns:
        frame = frame[columns]
    return _result(plan, frame, analysis_code="return detail rows with requested detail columns")


def _rank_top_n(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    step = plan["step_plan"][0]
    product_keys = plan["product_grain"]
    frame = pd.DataFrame(runtime_sources.get(step["source_alias"], []))
    if frame.empty:
        return _empty_result(plan, "No rows found for rank step")
    metric = step["metric"]
    grouped = _sum_by(frame, product_keys, metric)
    grouped["RANK"] = grouped[metric].rank(method="first", ascending=False).astype(int)
    grouped = grouped[grouped["RANK"] <= int(step["top_n"])].sort_values("RANK")
    return _result(
        plan,
        grouped[[*product_keys, metric, "RANK"]],
        analysis_code=f"groupby(product_grain).sum({metric}) -> rank desc -> top_n",
    )


def _equipment_for_previous_products(
    plan: dict[str, Any],
    runtime_sources: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    product_keys = plan["product_grain"]
    source_alias = plan["retrieval_jobs"][0]["source_alias"]
    frame = pd.DataFrame(runtime_sources.get(source_alias, []))
    if frame.empty:
        return _empty_result(plan, "No equipment rows found")
    product_tuples = plan.get("state_product_keys", [])
    if product_tuples:
        allowed = {tuple(item.get(key) for key in product_keys) for item in product_tuples}
        mask = frame.apply(lambda row: tuple(row.get(key) for key in product_keys) in allowed, axis=1)
        frame = frame[mask].copy()
    columns = ["EQPID", "EQP_MODEL", "PRESS_CNT", *product_keys, "LOT_ID", "RECIPE_ID"]
    columns = [column for column in columns if column in frame.columns]
    return _result(
        plan,
        frame[columns],
        analysis_code="read previous product grain from state -> filter equipment rows by product tuple -> detail rows",
    )


def _aggregate_join(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    product_keys = plan["product_grain"]
    prod = _sum_by(pd.DataFrame(runtime_sources.get("lpddr5_wb_production_today", [])), product_keys, "PRODUCTION")
    wip = _sum_by(pd.DataFrame(runtime_sources.get("lpddr5_wb_wip_today", [])), product_keys, "WIP")
    final = prod.merge(wip, on=product_keys, how="outer").fillna({"PRODUCTION": 0, "WIP": 0})
    final["PRODUCTION"] = final["PRODUCTION"].astype(int)
    final["WIP"] = final["WIP"].astype(int)
    return _result(
        plan,
        final[[*product_keys, "PRODUCTION", "WIP"]],
        analysis_code="aggregate production and WIP by product grain -> outer join by product grain",
        intermediate_refs={"production_by_product": _preview_frame(prod), "wip_by_product": _preview_frame(wip)},
    )


def _production_wip_target_rate(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    product_keys = plan["product_grain"]
    production = _sum_by(pd.DataFrame(runtime_sources.get("scope_production_today", [])), product_keys, "PRODUCTION")
    wip = _sum_by(pd.DataFrame(runtime_sources.get("scope_wip_today", [])), product_keys, "WIP")
    target = _sum_by(pd.DataFrame(runtime_sources.get("scope_target", [])), product_keys, "OUT_PLAN")
    final = production.merge(wip, on=product_keys, how="outer").merge(target, on=product_keys, how="outer")
    for column in ["PRODUCTION", "WIP", "OUT_PLAN"]:
        final[column] = final[column].fillna(0).astype(float)
    final["ACHIEVEMENT_RATE"] = final.apply(
        lambda row: round((row["PRODUCTION"] / row["OUT_PLAN"] * 100), 2) if row["OUT_PLAN"] else 0,
        axis=1,
    )
    final[["PRODUCTION", "WIP", "OUT_PLAN"]] = final[["PRODUCTION", "WIP", "OUT_PLAN"]].astype(int)
    return _result(
        plan,
        final[[*product_keys, "PRODUCTION", "WIP", "OUT_PLAN", "ACHIEVEMENT_RATE"]],
        analysis_code=(
            "aggregate PRODUCTION/WIP/OUT_PLAN by product grain -> join -> "
            "ACHIEVEMENT_RATE = sum(PRODUCTION) / sum(OUT_PLAN) * 100"
        ),
    )


def _lot_count_by_process(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    step = plan["step_plan"][0]
    frame = pd.DataFrame(runtime_sources.get(step["source_alias"], []))
    if frame.empty:
        return _empty_result(plan, "No lot rows found")
    result = (
        frame.groupby("OPER_SHORT_DESC", dropna=False)["LOT_ID"]
        .nunique()
        .reset_index(name="LOT_COUNT")
        .sort_values(["LOT_COUNT", "OPER_SHORT_DESC"], ascending=[False, True])
    )
    return _result(
        plan,
        result,
        analysis_code="groupby(OPER_SHORT_DESC).LOT_ID.nunique() -> LOT_COUNT",
    )


def _lot_quantity_summary(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    step = plan["step_plan"][0]
    frame = pd.DataFrame(runtime_sources.get(step["source_alias"], []))
    if frame.empty:
        return _empty_result(plan, "No DA lot rows found")
    result = pd.DataFrame(
        [
            {
                "SCOPE": "DA",
                "LOT_COUNT": int(frame["LOT_ID"].nunique()),
                "WF_QTY": int(pd.to_numeric(frame["WF_QTY"], errors="coerce").fillna(0).sum()),
                "DIE_QTY": int(pd.to_numeric(frame["SUB_PROD_QTY"], errors="coerce").fillna(0).sum()),
            }
        ]
    )
    return _result(
        plan,
        result,
        analysis_code="LOT_COUNT = LOT_ID.nunique(); WF_QTY/SUB_PROD_QTY aggregate by sum",
    )


def _aggregate_wip_total(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    frame = pd.DataFrame(runtime_sources.get("wip_total", []))
    total = int(pd.to_numeric(frame.get("WIP", pd.Series(dtype="float")), errors="coerce").fillna(0).sum())
    result = pd.DataFrame([{"SCOPE": plan.get("scope_label", "ALL"), "WIP": total}])
    return _result(plan, result, analysis_code="sum(WIP) for the requested scope")


def _low_output_vs_target(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    product_keys = plan["product_grain"]
    target_column = plan.get("target_column", "OUT_PLAN")
    threshold = float(plan.get("threshold_percent", 90.0))
    production = _sum_by(pd.DataFrame(runtime_sources.get("low_output_production", [])), product_keys, "PRODUCTION")
    target = _sum_by(pd.DataFrame(runtime_sources.get("low_output_target", [])), product_keys, target_column)
    final = production.merge(target, on=product_keys, how="outer")
    final["PRODUCTION"] = pd.to_numeric(final["PRODUCTION"], errors="coerce").fillna(0)
    final[target_column] = pd.to_numeric(final[target_column], errors="coerce").fillna(0)
    final["TARGET_QTY"] = final[target_column]
    final["ACHIEVEMENT_RATE"] = final.apply(
        lambda row: round((row["PRODUCTION"] / row["TARGET_QTY"] * 100), 2) if row["TARGET_QTY"] else 0,
        axis=1,
    )
    final["BALANCE"] = (final["TARGET_QTY"] - final["PRODUCTION"]).clip(lower=0)
    final["LOW_OUTPUT_FLAG"] = final["ACHIEVEMENT_RATE"] < threshold
    final = final[final["LOW_OUTPUT_FLAG"]].copy()
    for column in ["PRODUCTION", "TARGET_QTY", "BALANCE"]:
        final[column] = final[column].astype(int)
    final = final.sort_values(["ACHIEVEMENT_RATE", "BALANCE"], ascending=[True, False])
    return _result(
        plan,
        final[[*product_keys, "PRODUCTION", "TARGET_QTY", "ACHIEVEMENT_RATE", "BALANCE", "LOW_OUTPUT_FLAG"]],
        analysis_code=(
            "aggregate PRODUCTION and target by product grain -> "
            "ACHIEVEMENT_RATE = PRODUCTION / TARGET_QTY * 100 -> filter below threshold"
        ),
    )


def _date_split_production_plan_gap(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    product_keys = plan["product_grain"]
    production = _sum_by(pd.DataFrame(runtime_sources.get("yesterday_production", [])), product_keys, "PRODUCTION")
    target = _sum_by(pd.DataFrame(runtime_sources.get("today_target", [])), product_keys, "OUT_PLAN")
    final = production.merge(target, on=product_keys, how="outer")
    final["PRODUCTION"] = pd.to_numeric(final["PRODUCTION"], errors="coerce").fillna(0)
    final["OUT_PLAN"] = pd.to_numeric(final["OUT_PLAN"], errors="coerce").fillna(0)
    final["BALANCE"] = (final["OUT_PLAN"] - final["PRODUCTION"]).astype(int)
    final[["PRODUCTION", "OUT_PLAN"]] = final[["PRODUCTION", "OUT_PLAN"]].astype(int)
    return _result(
        plan,
        final[[*product_keys, "PRODUCTION", "OUT_PLAN", "BALANCE"]],
        analysis_code="yesterday production and today target keep separate dates -> join by product grain -> BALANCE",
    )


def _overall_production_wip_target(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    production = _sum_metric(runtime_sources.get("total_production_today", []), "PRODUCTION")
    wip = _sum_metric(runtime_sources.get("total_wip_today", []), "WIP")
    target = _sum_metric(runtime_sources.get("total_target", []), "OUT_PLAN")
    frame = pd.DataFrame([{"SCOPE": "ALL", "PRODUCTION": production, "WIP": wip, "OUT_PLAN": target}])
    return _result(plan, frame, analysis_code="sum each dataset independently and return one total row")


def _equipment_by_model(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    frame = pd.DataFrame(runtime_sources.get("hbm_equipment_status", []))
    if frame.empty:
        return _empty_result(plan, "No HBM equipment rows found")
    frame["PRESS_CNT"] = pd.to_numeric(frame["PRESS_CNT"], errors="coerce").fillna(0)
    result = (
        frame.groupby("EQP_MODEL", dropna=False)
        .agg(EQP_COUNT=("EQPID", "nunique"), PRESS_CNT=("PRESS_CNT", "sum"))
        .reset_index()
        .sort_values(["PRESS_CNT", "EQP_MODEL"], ascending=[False, True])
    )
    result["PRESS_CNT"] = result["PRESS_CNT"].astype(int)
    return _result(
        plan,
        result,
        analysis_code="filter HBM equipment rows -> groupby(EQP_MODEL).agg(EQP_COUNT=nunique, PRESS_CNT=sum)",
    )


def _sum_by(frame: pd.DataFrame, group_by: list[str], metric: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=[*group_by, metric])
    clean = frame.copy()
    clean[metric] = pd.to_numeric(clean[metric], errors="coerce").fillna(0)
    return clean.groupby(group_by, dropna=False, as_index=False)[metric].sum()


def _sum_metric(rows: list[dict[str, Any]], metric: str) -> int:
    frame = pd.DataFrame(rows)
    if frame.empty or metric not in frame:
        return 0
    return int(pd.to_numeric(frame[metric], errors="coerce").fillna(0).sum())


def _rank_group_for_process(process_name: Any, rank_groups: list[dict[str, Any]]) -> str | None:
    for group in rank_groups:
        if process_name in set(group.get("values", [])):
            return group["label"]
    return None


def _key_frame(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=keys)
    return frame[keys].drop_duplicates()


def _result(
    plan: dict[str, Any],
    frame: pd.DataFrame,
    analysis_code: str,
    intermediate_refs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = frame.to_dict(orient="records")
    return {
        "status": "ok",
        "analysis_kind": plan.get("analysis_kind"),
        "analysis_code": analysis_code,
        "columns": list(frame.columns),
        "rows": rows,
        "row_count": len(rows),
        "intermediate_refs": intermediate_refs or {},
        "errors": [],
    }


def _empty_result(plan: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "status": "empty",
        "analysis_kind": plan.get("analysis_kind"),
        "analysis_code": "",
        "columns": [],
        "rows": [],
        "row_count": 0,
        "intermediate_refs": {},
        "errors": [message],
    }


def _preview_frame(frame: pd.DataFrame, limit: int = 5) -> dict[str, Any]:
    return {"row_count": len(frame), "columns": list(frame.columns), "preview_rows": frame.head(limit).to_dict(orient="records")}
