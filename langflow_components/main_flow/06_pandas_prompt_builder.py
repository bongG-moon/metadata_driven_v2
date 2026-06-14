from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def build_pandas_prompt_payload(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    runtime_sources = payload.get("runtime_sources") if isinstance(payload.get("runtime_sources"), dict) else {}
    source_summary = _source_summary(runtime_sources)

    prompt = "\n".join(
        [
            "You are the pandas code generation node for a Langflow manufacturing data agent.",
            "Return one strict JSON object only. Do not wrap it in markdown.",
            "Generate Python pandas code that uses only the provided variables: pd, sources, plan, state.",
            "sources is a dict mapping source_alias to pandas DataFrame.",
            "plan and state are Python dicts. Use plan['key'], plan.get('key'), state.get('key'); never use plan.key or state.key.",
            "The code must assign the final pandas DataFrame to result_df.",
            "Final result columns must use the standard contract names requested by the normalized plan.",
            "Do not translate measure columns to Korean labels, and do not keep temporary names such as PRODUCTION_sum, WIP_sum, OUT_PLAN_sum, or lowercase rank in result_df.",
            "Do not import modules. Do not read/write files. Do not use network, OS, eval, exec, open, or subprocess.",
            "Do not use numpy, np, or np.where. Use pandas Series operations such as div, fillna, where, mask, and boolean comparisons.",
            "Do not use pd.inf, float('inf'), or infinity replacement. Avoid division by zero with boolean masks before dividing.",
            "If the generated code contains any import statement, the safety check will fail.",
            "",
            "User question:",
            str(request.get("question") or ""),
            "",
            "Normalized intent plan:",
            json.dumps(plan, ensure_ascii=False, indent=2),
            "",
            "Available source DataFrames:",
            json.dumps(source_summary, ensure_ascii=False, indent=2),
            "",
            "Previous state summary:",
            json.dumps(_state_summary(state), ensure_ascii=False, indent=2),
            "",
            "Analysis instruction:",
            _analysis_instruction(plan),
            "",
            "Required JSON schema:",
            json.dumps(
                {
                    "code": "Python code. It must set result_df.",
                    "output_columns": ["column names expected in result_df"],
                    "reasoning_steps": ["short reasoning steps"],
                },
                ensure_ascii=False,
                indent=2,
            ),
        ]
    )
    return {"prompt": prompt, "payload": payload, "prompt_type": "pandas_code", "source_summary": source_summary}


def _analysis_instruction(plan: dict[str, Any]) -> str:
    kind = plan.get("analysis_kind")
    product_keys = plan.get("product_grain", [])
    if kind == "rank_wip_then_join_production":
        return (
            "Assign RANK_GROUP from step_plan[0].rank_groups, aggregate WIP by RANK_GROUP and product_grain, "
            "rank each RANK_GROUP descending, keep top_n, aggregate PRODUCTION for ranked product keys, then left join. "
            "This is a multi-step question: first identify ranked products from WIP, then retrieve/aggregate production for those products. "
            f"The final result_df columns must be exactly ['RANK_GROUP', 'WIP_RANK'] + product_grain {product_keys} "
            "+ ['WIP', 'PRODUCTION']. Do not output PRODUCTION_sum or rank."
        )
    if kind == "detail_rows":
        return (
            "Return detail source rows without aggregation or groupby. "
            "If step_plan[0].source_aliases exists, return rows from those aliases and add SOURCE_ALIAS so each row's source is clear; "
            "otherwise return the requested detail columns from step_plan[0].source_alias."
        )
    if kind == "rank_top_n":
        return f"Aggregate the metric in step_plan[0].metric by product_grain {product_keys}, rank descending, keep top_n."
    if kind == "equipment_for_previous_products":
        return "Filter equipment rows by plan.state_product_keys using product_grain, then return equipment detail columns."
    if kind == "aggregate_join":
        return "Aggregate PRODUCTION and WIP by product_grain from their source aliases, then outer join by product_grain."
    if kind == "production_wip_target_rate":
        return (
            "Aggregate PRODUCTION, WIP, and OUT_PLAN by product_grain, join them, and calculate ACHIEVEMENT_RATE. "
            f"The final result_df columns must be exactly product_grain {product_keys} plus "
            "['WIP', 'PRODUCTION', 'OUT_PLAN', 'ACHIEVEMENT_RATE']."
        )
    if kind == "low_output_vs_target":
        return (
            "Aggregate PRODUCTION and plan['target_column'] by product_grain. Rename the selected target measure "
            "to TARGET_QTY in the final result, even when the source column is INPUT_PLAN or OUT_PLAN. "
            "Calculate ACHIEVEMENT_RATE=PRODUCTION/TARGET_QTY, BALANCE=PRODUCTION-TARGET_QTY, and "
            "LOW_OUTPUT_FLAG=ACHIEVEMENT_RATE < plan.get('threshold', 1.0). "
            "When TARGET_QTY is zero, set ACHIEVEMENT_RATE to 0 using boolean masks; do not use pd.inf, float('inf'), numpy, or np.where. "
            f"The final result_df columns must be exactly product_grain {product_keys} plus "
            "['PRODUCTION', 'TARGET_QTY', 'ACHIEVEMENT_RATE', 'BALANCE', 'LOW_OUTPUT_FLAG']."
        )
    if kind == "lot_count_by_process":
        return "Group lot_status rows by OPER_SHORT_DESC and calculate LOT_COUNT as LOT_ID.nunique()."
    if kind == "lot_quantity_summary":
        return (
            "Return one row with LOT_COUNT=LOT_ID.nunique(), WF_QTY=sum(WF_QTY), DIE_QTY=sum(SUB_PROD_QTY). "
            "The final result_df columns must be exactly ['LOT_COUNT', 'WF_QTY', 'DIE_QTY']."
        )
    if kind == "aggregate_wip_total":
        return "Return one row with SCOPE=plan.scope_label or ALL and WIP=sum(WIP)."
    if kind == "overall_production_wip_target":
        return (
            "Sum PRODUCTION, WIP, and OUT_PLAN independently and return one row. "
            "Do not rename OUT_PLAN to TARGET. The final result_df columns must include ['PRODUCTION', 'WIP', 'OUT_PLAN']; "
            "if you add SCOPE, set it to ALL."
        )
    if kind == "date_split_production_plan_gap":
        return (
            "Aggregate yesterday PRODUCTION and today OUT_PLAN by product_grain, join by product_grain, and calculate "
            "BALANCE=OUT_PLAN-PRODUCTION. In the final result, keep the measure columns named PRODUCTION, OUT_PLAN, "
            f"and BALANCE. The final result_df columns must be exactly product_grain {product_keys} plus "
            "['PRODUCTION', 'OUT_PLAN', 'BALANCE']; do not use names like yesterday_PRODUCTION or today_OUT_PLAN."
        )
    if kind == "equipment_by_model":
        return (
            "Group equipment rows by EQP_MODEL, calculate EQP_COUNT=EQPID.nunique() and PRESS_CNT=sum(PRESS_CNT). "
            "The final result_df columns must be exactly ['EQP_MODEL', 'EQP_COUNT', 'PRESS_CNT']; "
            "do not rename PRESS_CNT to TOTAL_PRESS_CNT and do not omit EQP_COUNT."
        )
    return "Return an empty DataFrame with no rows."


def _source_summary(runtime_sources: dict[str, Any]) -> dict[str, Any]:
    summary = {}
    for alias, rows in runtime_sources.items():
        clean_rows = rows if isinstance(rows, list) else []
        first_row = clean_rows[0] if clean_rows and isinstance(clean_rows[0], dict) else {}
        summary[str(alias)] = {
            "row_count": len(clean_rows),
            "columns": list(first_row.keys()),
            "preview_rows": deepcopy(clean_rows[:5]),
        }
    return summary


def _state_summary(state: dict[str, Any]) -> dict[str, Any]:
    current_data = state.get("current_data") if isinstance(state.get("current_data"), dict) else {}
    rows = _rows_from_current_data(current_data)
    return {
        "has_state": bool(state),
        "context": state.get("context", {}),
        "current_data_columns": current_data.get("columns", []),
        "current_data_row_count": current_data.get("row_count", 0),
        "current_data_preview_rows": rows[:3],
        "current_data_product_key_columns": current_data.get("product_key_columns", []),
        "current_data_product_key_values": _list_preview(current_data.get("product_key_values"), 20),
        "current_data_product_key_count": current_data.get("product_key_count", 0),
        "followup_source_results": state.get("followup_source_results", []),
    }


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


def _rows_from_current_data(current_data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = current_data.get("rows")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    data = current_data.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        return [row for row in data["rows"] if isinstance(row, dict)]
    return []


def _list_preview(value: Any, limit: int) -> list[Any]:
    return deepcopy(value[:limit]) if isinstance(value, list) else []


class PandasPromptBuilder(Component):
    display_name = "06 Pandas Prompt Builder"
    description = "Builds the prompt that should be sent to the Langflow Gemini/LLM node for pandas code generation."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="pandas_prompt", display_name="Pandas Prompt", method="build_prompt"),
        Output(name="prompt_payload", display_name="Prompt Payload", method="build_prompt_payload"),
    ]

    def build_prompt(self) -> Message:
        prompt_payload = build_pandas_prompt_payload(getattr(self, "payload", None))
        self.status = {
            "prompt_type": "pandas_code",
            "chars": len(prompt_payload["prompt"]),
            "sources": list(prompt_payload.get("source_summary", {}).keys()),
        }
        return Message(text=prompt_payload["prompt"])

    def build_prompt_payload(self) -> Data:
        return Data(data=build_pandas_prompt_payload(getattr(self, "payload", None)))
