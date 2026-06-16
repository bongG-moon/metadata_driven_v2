from __future__ import annotations

import ast
import json
import re
from copy import deepcopy
from typing import Any

import pandas as pd
from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


FORBIDDEN_CALL_NAMES = {
    "__import__",
    "compile",
    "eval",
    "exec",
    "getattr",
    "globals",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}
FORBIDDEN_ROOT_NAMES = {
    "__builtins__",
    "builtins",
    "importlib",
    "io",
    "np",
    "numpy",
    "os",
    "pathlib",
    "pickle",
    "requests",
    "socket",
    "subprocess",
    "sys",
}


def execute_pandas_from_llm(payload_value: Any, llm_response_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    if payload.get("direct_response_ready"):
        return payload
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    runtime_sources = payload.get("runtime_sources") if isinstance(payload.get("runtime_sources"), dict) else {}

    llm_text = _text(llm_response_value)
    pandas_json = _extract_json_object(llm_text)
    analysis = _execute_generated_pandas_code(pandas_json, plan, runtime_sources, state)
    analysis["pandas_code_json"] = pandas_json
    analysis["llm_text_preview"] = llm_text[:1200]

    next_payload = dict(payload)
    next_payload["analysis"] = analysis
    if analysis.get("errors"):
        next_payload["warnings"] = list(next_payload.get("warnings", [])) + [
            f"pandas_executor: {item}" for item in analysis["errors"]
        ]
    return next_payload


def _execute_generated_pandas_code(
    pandas_plan: dict[str, Any],
    plan: dict[str, Any],
    runtime_sources: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    code = _strip_harmless_pandas_import(str(pandas_plan.get("code", "")))
    safety_errors = _check_code_safety(code)
    if safety_errors:
        return {
            "status": "error",
            "analysis_kind": plan.get("analysis_kind"),
            "analysis_code": code,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "intermediate_refs": {},
            "errors": safety_errors,
            "safety_passed": False,
            "executed": False,
        }

    required_columns_by_alias = _required_columns_by_alias(plan)
    sources = {
        alias: _source_dataframe(
            rows if isinstance(rows, list) else [],
            required_columns_by_alias.get(str(alias), []),
            str(plan.get("analysis_kind") or ""),
        )
        for alias, rows in runtime_sources.items()
    }
    local_vars: dict[str, Any] = {"pd": pd, "sources": sources, "plan": deepcopy(plan), "state": deepcopy(state)}
    safe_globals = {"__builtins__": _safe_builtins(), "pd": pd}
    try:
        exec(compile(code, "<llm_pandas_code>", "exec"), safe_globals, local_vars)
        result_df = local_vars.get("result_df")
        if result_df is None or not hasattr(result_df, "to_dict"):
            raise ValueError("Generated code must assign a pandas DataFrame to result_df.")
        result_df = result_df.copy()
        result_df = _normalize_result_columns(result_df, plan)
    except Exception as exc:
        fallback_df = _fallback_result_df(plan, runtime_sources)
        if fallback_df is None:
            return {
                "status": "error",
                "analysis_kind": plan.get("analysis_kind"),
                "analysis_code": code,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "intermediate_refs": {},
                "errors": [f"Generated pandas code failed: {exc}"],
                "safety_passed": True,
                "executed": False,
            }
        result_df = _normalize_result_columns(fallback_df, plan)
        code = code + f"\n# executor_fallback: {exc}"

    rows = result_df.to_dict(orient="records")
    product_key_columns = _product_key_columns(plan, list(result_df.columns))
    product_key_values = _product_key_values(rows, product_key_columns)
    return {
        "status": "ok",
        "analysis_kind": plan.get("analysis_kind"),
        "analysis_code": code,
        "columns": list(result_df.columns),
        "rows": _json_ready(rows),
        "row_count": len(rows),
        "product_key_columns": product_key_columns,
        "product_key_values": product_key_values,
        "product_key_count": len(product_key_values),
        "intermediate_refs": {},
        "errors": [],
        "safety_passed": True,
        "executed": True,
        "output_columns": pandas_plan.get("output_columns", []),
        "reasoning_steps": pandas_plan.get("reasoning_steps", []),
    }


def _normalize_result_columns(frame: pd.DataFrame, plan: dict[str, Any]) -> pd.DataFrame:
    result = frame.copy()
    rename_map: dict[str, str] = {}
    analysis_kind = plan.get("analysis_kind")

    for base_name in ["PRODUCTION", "WIP", "OUT_PLAN", "TARGET_QTY", "LOT_COUNT", "WF_QTY", "DIE_QTY", "PRESS_CNT"]:
        for suffix in ("_sum", "_total", "_quantity", "_qty"):
            alias = f"{base_name}{suffix}"
            if base_name not in result.columns and alias in result.columns:
                rename_map[alias] = base_name

    structural_alias_map = {
        "WIP": ["TOTAL_WIP", "WIP_TOTAL", "WIP_SUM", "SUM_WIP", "WIP_QUANTITY", "WIP_QTY"],
        "PRODUCTION": ["PRODUCTION_QUANTITY", "PRODUCTION_QTY"],
        "PRESS_CNT": ["TOTAL_PRESS_CNT", "PRESS_COUNT"],
        "WF_QTY": ["WAFER_QTY", "WAFER_COUNT", "WF_COUNT"],
        "DIE_QTY": ["DIE_COUNT"],
        "EQP_COUNT": ["EQUIPMENT_COUNT", "EQP_CNT"],
    }
    for standard_name, aliases in structural_alias_map.items():
        if standard_name in result.columns:
            continue
        for alias in aliases:
            if alias in result.columns:
                rename_map[alias] = standard_name
                break
    if analysis_kind == "lot_quantity_summary" and "DIE_QTY" not in result.columns and "SUB_PROD_QTY" in result.columns:
        rename_map["SUB_PROD_QTY"] = "DIE_QTY"
    if analysis_kind == "lot_count_by_process" and "OPER_SHORT_DESC" not in result.columns and "OPER_NAME" in result.columns:
        rename_map["OPER_NAME"] = "OPER_SHORT_DESC"

    if analysis_kind == "rank_wip_then_join_production":
        if "WIP_RANK" not in result.columns and "rank" in result.columns:
            rename_map["rank"] = "WIP_RANK"
        if "PRODUCTION" not in result.columns and "PRODUCTION_total" in result.columns:
            rename_map["PRODUCTION_total"] = "PRODUCTION"

    alias_map = {
        "PRODUCTION": ["생산량", "생산 수량", "실적", "생산실적"],
        "WIP": ["재공", "재공 수량", "재공수량"],
        "OUT_PLAN": ["목표값", "목표", "생산계획", "계획", "OUT계획"],
        "TARGET_QTY": ["목표수량", "목표 수량", "계획수량", "계획 수량"],
        "ACHIEVEMENT_RATE": ["생산달성율", "생산달성률", "달성율", "달성률"],
        "BALANCE": ["차이수량", "부족수량", "미달수량"],
        "LOT_COUNT": ["Lot 수량", "LOT 수량", "lot 수량", "lot수량"],
    }
    for standard_name, aliases in alias_map.items():
        if standard_name in result.columns:
            continue
        for alias in aliases:
            if alias in result.columns:
                rename_map[alias] = standard_name
                break

    if rename_map:
        result = result.rename(columns=rename_map)
    if analysis_kind == "rank_wip_then_join_production" and "RANK_GROUP" not in result.columns and "OPER_NAME" in result.columns:
        result.insert(0, "RANK_GROUP", result["OPER_NAME"].map(_rank_group_from_oper_name))
    if analysis_kind == "aggregate_wip_total" and "SCOPE" not in result.columns and "WIP" in result.columns:
        result.insert(0, "SCOPE", plan.get("scope_label") or "ALL")
    return _order_result_columns(result, plan)


def _fallback_result_df(plan: dict[str, Any], runtime_sources: dict[str, Any]) -> pd.DataFrame | None:
    if str(plan.get("analysis_kind") or "") != "lot_quantity_summary":
        return None
    alias = _primary_source_alias(plan, runtime_sources)
    rows = runtime_sources.get(alias) if alias else None
    if not isinstance(rows, list):
        return None
    frame = _source_dataframe(rows, [], str(plan.get("analysis_kind") or ""))
    lot_count = frame["LOT_ID"].nunique() if "LOT_ID" in frame.columns else 0
    wf_qty = frame["WF_QTY"].sum() if "WF_QTY" in frame.columns else 0
    die_source = "SUB_PROD_QTY" if "SUB_PROD_QTY" in frame.columns else "DIE_QTY"
    die_qty = frame[die_source].sum() if die_source in frame.columns else 0
    return pd.DataFrame([{"LOT_COUNT": lot_count, "WF_QTY": wf_qty, "DIE_QTY": die_qty}])


def _primary_source_alias(plan: dict[str, Any], runtime_sources: dict[str, Any]) -> str:
    for step in plan.get("step_plan", []) if isinstance(plan.get("step_plan"), list) else []:
        if isinstance(step, dict) and step.get("source_alias") in runtime_sources:
            return str(step["source_alias"])
    for alias in runtime_sources:
        return str(alias)
    return ""


def _rank_group_from_oper_name(value: Any) -> str:
    text = str(value or "")
    upper = text.upper()
    if upper.startswith("D/A") or upper.startswith("DA"):
        return "DA"
    if upper.startswith("W/B") or upper.startswith("WB"):
        return "WB"
    return text


def _order_result_columns(frame: pd.DataFrame, plan: dict[str, Any]) -> pd.DataFrame:
    preferred = _preferred_columns(plan)
    if not preferred:
        return frame
    ordered = [column for column in preferred if column in frame.columns]
    remaining = [column for column in frame.columns if column not in ordered]
    return frame[ordered + remaining]


def _product_key_columns(plan: dict[str, Any], columns: list[Any]) -> list[str]:
    available = [str(column) for column in columns]
    plan_grain = plan.get("product_grain") if isinstance(plan.get("product_grain"), list) else []
    if plan_grain:
        return [str(column) for column in plan_grain if str(column) in available]
    default_keys = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "TSV_DIE_TYP"]
    return [column for column in default_keys if column in available]


def _product_key_values(rows: list[dict[str, Any]], product_key_columns: list[str]) -> list[dict[str, Any]]:
    if not product_key_columns:
        return []
    values: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        product = {key: row.get(key) for key in product_key_columns if row.get(key) not in {None, ""}}
        if product and product not in values:
            values.append(product)
    return values


def _preferred_columns(plan: dict[str, Any]) -> list[str]:
    product_keys = plan.get("product_grain") if isinstance(plan.get("product_grain"), list) else []
    kind = plan.get("analysis_kind")
    if kind == "rank_wip_then_join_production":
        return ["RANK_GROUP", "WIP_RANK", *product_keys, "WIP", "PRODUCTION"]
    if kind == "aggregate_join":
        return [*product_keys, "PRODUCTION", "WIP"]
    if kind == "production_wip_target_rate":
        return [*product_keys, "WIP", "PRODUCTION", "OUT_PLAN", "ACHIEVEMENT_RATE"]
    if kind == "low_output_vs_target":
        return [*product_keys, "PRODUCTION", "TARGET_QTY", "ACHIEVEMENT_RATE", "BALANCE", "LOW_OUTPUT_FLAG"]
    if kind == "lot_count_by_process":
        return ["OPER_SHORT_DESC", "LOT_COUNT"]
    if kind == "lot_quantity_summary":
        return ["LOT_COUNT", "WF_QTY", "DIE_QTY"]
    if kind == "aggregate_wip_total":
        return ["SCOPE", "WIP"]
    if kind == "overall_production_wip_target":
        return ["SCOPE", "PRODUCTION", "WIP", "OUT_PLAN"]
    if kind == "date_split_production_plan_gap":
        return [*product_keys, "PRODUCTION", "OUT_PLAN", "BALANCE"]
    if kind == "equipment_by_model":
        return ["EQP_MODEL", "EQP_COUNT", "PRESS_CNT"]
    if kind == "equipment_count_for_previous_products":
        return [*product_keys, "EQP_COUNT"]
    return []


def _source_dataframe(
    rows: list[dict[str, Any]],
    required_columns: list[str] | None = None,
    analysis_kind: str = "",
) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty:
        frame = pd.DataFrame(columns=[str(column) for column in (required_columns or [])])
    frame = _drop_redundant_alias_columns(frame)
    return _add_missing_required_columns(frame, required_columns or [], analysis_kind)


def _required_columns_by_alias(plan: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for job in plan.get("retrieval_jobs", []) if isinstance(plan.get("retrieval_jobs"), list) else []:
        if not isinstance(job, dict):
            continue
        alias = str(job.get("source_alias") or job.get("dataset_key") or "")
        columns = job.get("required_columns") if isinstance(job.get("required_columns"), list) else []
        if alias:
            result[alias] = _unique_columns([str(column) for column in columns if str(column or "").strip()])
    return result


def _add_missing_required_columns(frame: pd.DataFrame, required_columns: list[str], analysis_kind: str) -> pd.DataFrame:
    if not required_columns:
        return frame
    result = frame.copy()
    existing = set(str(column) for column in result.columns)
    for column in required_columns:
        text = str(column or "").strip()
        if not text or text in existing:
            continue
        standard = _standard_column_for_alias(text)
        if analysis_kind != "detail_rows" and standard and standard in existing:
            continue
        result[text] = None
        existing.add(text)
    return result


def _drop_redundant_alias_columns(frame: pd.DataFrame) -> pd.DataFrame:
    alias_columns = {
        "MODE": ["Mode", "PROD_TYP"],
        "PKG_TYPE1": ["PKG1", "PKG_TYP"],
        "PKG_TYPE2": ["PKG2", "PKG_TYP_2", "PKG_TYP2"],
        "MCP_NO": ["MCP NO", "MCPSALENO", "PROD_GRP_ID", "MCP_SALE_CD"],
        "TECH": ["TECH_NM"],
        "DEN": ["DEN_TYP"],
        "LEAD": ["LEAD_CNT"],
        "INPUT_PLAN": ["INPUT계획"],
        "OUT_PLAN": ["OUT계획", "TARGET"],
        "EQP_MODEL": ["EQP_MODEL_CD"],
    }
    drop_columns: list[str] = []
    existing = set(str(column) for column in frame.columns)
    for standard, aliases in alias_columns.items():
        if standard not in existing:
            continue
        for alias in aliases:
            if alias in existing:
                drop_columns.append(alias)
    if not drop_columns:
        return frame
    return frame.drop(columns=drop_columns, errors="ignore")


def _standard_column_for_alias(alias: str) -> str:
    alias_to_standard = {
        "Mode": "MODE",
        "PROD_TYP": "MODE",
        "PKG1": "PKG_TYPE1",
        "PKG_TYP": "PKG_TYPE1",
        "PKG2": "PKG_TYPE2",
        "PKG_TYP_2": "PKG_TYPE2",
        "PKG_TYP2": "PKG_TYPE2",
        "MCP NO": "MCP_NO",
        "MCPSALENO": "MCP_NO",
        "PROD_GRP_ID": "MCP_NO",
        "MCP_SALE_CD": "MCP_NO",
        "TECH_NM": "TECH",
        "DEN_TYP": "DEN",
        "LEAD_CNT": "LEAD",
        "INPUT계획": "INPUT_PLAN",
        "OUT계획": "OUT_PLAN",
        "TARGET": "OUT_PLAN",
        "EQP_MODEL_CD": "EQP_MODEL",
    }
    return alias_to_standard.get(alias, "")


def _unique_columns(columns: list[str]) -> list[str]:
    result = []
    for column in columns:
        if column not in result:
            result.append(column)
    return result


def _strip_harmless_pandas_import(code: str) -> str:
    lines = []
    for line in code.splitlines():
        stripped = line.strip()
        if stripped in {"import pandas as pd", "import pandas"}:
            continue
        lines.append(line)
    return _rewrite_pandas_compatibility("\n".join(lines).strip())


def _rewrite_pandas_compatibility(code: str) -> str:
    # Some LLMs emit NumPy-style infinity through pandas. pandas 2.x has no pd.inf.
    return re.sub(r"(?<![\w.])pd\.inf\b", 'float("inf")', code, flags=re.IGNORECASE)


def _check_code_safety(code: str) -> list[str]:
    if not code:
        return ["Generated pandas code is empty."]
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"Generated pandas code has syntax error: {exc}"]

    errors = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            errors.append("Imports are not allowed in generated pandas code.")
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in FORBIDDEN_CALL_NAMES:
                errors.append(f"Forbidden call: {name}")
            root = name.split(".", 1)[0] if name else ""
            if root in FORBIDDEN_ROOT_NAMES:
                errors.append(f"Forbidden call root: {root}")
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_ROOT_NAMES:
            errors.append(f"Forbidden name: {node.id}")
        if isinstance(node, ast.Attribute):
            value_name = _root_name(node.value)
            if value_name in FORBIDDEN_ROOT_NAMES:
                errors.append(f"Forbidden attribute root: {value_name}")
    return sorted(set(errors))


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        prefix = _call_name(func.value)
        return f"{prefix}.{func.attr}" if prefix else func.attr
    return ""


def _root_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _root_name(node.value)
    return ""


def _safe_builtins() -> dict[str, Any]:
    return {
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "range": range,
        "round": round,
        "set": set,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "zip": zip,
    }


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(raw[index:])
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _json_ready(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return str(value)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        for key in ("llm_text", "text", "content", "response"):
            if data.get(key):
                return str(data[key])
    for attr in ("text", "content"):
        if getattr(value, attr, None):
            return str(getattr(value, attr))
    return str(value)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


class PandasCodeExecutor(Component):
    display_name = "15 Pandas Code Executor"
    description = "Parses Gemini/LLM pandas JSON, checks code safety, and executes it against runtime source DataFrames."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="llm_response", display_name="LLM Response", required=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        result = execute_pandas_from_llm(getattr(self, "payload", None), getattr(self, "llm_response", ""))
        analysis = result.get("analysis", {})
        self.status = {
            "status": analysis.get("status"),
            "rows": analysis.get("row_count", 0),
            "safety_passed": analysis.get("safety_passed", False),
            "executed": analysis.get("executed", False),
            "errors": len(analysis.get("errors", [])),
        }
        return Data(data=result)
