from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


def normalize_intent_payload(payload_value: Any, llm_response_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    llm_text = _text(llm_response_value)
    llm_json = _extract_json_object(llm_text)
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    catalog = ((metadata.get("table_catalog") or {}).get("datasets") or {}) if isinstance(metadata, dict) else {}
    product_grain = ((metadata.get("domain_items") or {}).get("product_key_columns") or []) if isinstance(metadata, dict) else []

    errors: list[str] = []
    notes: list[str] = []
    if not llm_json:
        errors.append("Intent LLM response did not contain a JSON object.")
    plan = _base_plan(llm_json, product_grain)
    _attach_state_product_keys(plan, payload)
    plan["llm_intent_json"] = llm_json
    plan["llm_text_preview"] = llm_text[:1200]

    normalized_jobs = []
    raw_jobs = plan.get("retrieval_jobs", [])
    if not raw_jobs and plan.get("intent_type") != "finish":
        raw_jobs = _fallback_retrieval_jobs(plan, llm_json, metadata, payload)
        if raw_jobs:
            notes.append("retrieval_jobs were missing; built fallback jobs from analysis_kind, datasets, metadata, and request context.")
        else:
            errors.append("No retrieval_jobs were provided and fallback job generation could not determine datasets.")
    for index, raw_job in enumerate(raw_jobs):
        if not isinstance(raw_job, dict):
            continue
        dataset_key = str(raw_job.get("dataset_key") or "").strip()
        if not dataset_key:
            errors.append(f"retrieval_jobs[{index}] is missing dataset_key.")
            continue
        dataset_catalog = catalog.get(dataset_key) if isinstance(catalog.get(dataset_key), dict) else {}
        job = deepcopy(raw_job)
        job.setdefault("job_id", f"job_{index + 1}_{dataset_key}")
        job.setdefault("source_alias", dataset_key)
        job.setdefault("params", _params_for_dataset(llm_json, dataset_key))
        job.setdefault("filters", [])
        job.setdefault("required_columns", dataset_catalog.get("columns", []))
        job["source_type"] = dataset_catalog.get("source_type", job.get("source_type", "dummy"))
        normalized_jobs.append(job)
    plan["retrieval_jobs"] = normalized_jobs
    plan["datasets"] = _unique([job["dataset_key"] for job in normalized_jobs] or llm_json.get("datasets", []))
    if not plan.get("step_plan"):
        fallback_steps = _fallback_step_plan(plan)
        if fallback_steps:
            plan["step_plan"] = fallback_steps
            notes.append("step_plan was missing; built a minimal fallback step_plan from retrieval aliases.")
    plan["route"] = _route_for_intent(plan.get("intent_type"), len(normalized_jobs))
    plan["normalizer_errors"] = errors
    plan["normalizer_notes"] = notes

    next_payload = dict(payload)
    next_payload["intent_plan"] = plan
    next_payload["retrieval_jobs"] = normalized_jobs
    next_payload["metadata_context"] = _metadata_context(plan)
    if errors:
        next_payload["warnings"] = list(next_payload.get("warnings", [])) + [f"intent_normalizer: {item}" for item in errors]
    if notes:
        next_payload["warnings"] = list(next_payload.get("warnings", [])) + [f"intent_normalizer: {item}" for item in notes]
    return next_payload


def _base_plan(llm_json: dict[str, Any], product_grain: list[str]) -> dict[str, Any]:
    intent_type = str(llm_json.get("intent_type") or "single_retrieval_analysis").strip()
    analysis_kind = str(llm_json.get("analysis_kind") or "none").strip()
    step_plan = llm_json.get("step_plan") if isinstance(llm_json.get("step_plan"), list) else []
    retrieval_jobs = llm_json.get("retrieval_jobs") if isinstance(llm_json.get("retrieval_jobs"), list) else []
    plan = {
        "intent_type": intent_type,
        "analysis_kind": analysis_kind,
        "product_grain": llm_json.get("product_grain") if isinstance(llm_json.get("product_grain"), list) else product_grain,
        "datasets": _unique(llm_json.get("datasets", [])),
        "params_by_dataset": llm_json.get("params_by_dataset", {}) if isinstance(llm_json.get("params_by_dataset"), dict) else {},
        "filters": llm_json.get("filters", []) if isinstance(llm_json.get("filters"), list) else [],
        "retrieval_jobs": retrieval_jobs,
        "step_plan": step_plan,
        "depends_on_state": bool(llm_json.get("depends_on_state", False)),
        "reasoning_steps": llm_json.get("reasoning_steps", []) if isinstance(llm_json.get("reasoning_steps"), list) else [],
    }
    for key in (
        "analysis_output_shape",
        "rank_groups",
        "scope_label",
        "state_product_keys",
        "target_column",
        "threshold",
        "threshold_percent",
        "top_n",
    ):
        if key in llm_json:
            plan[key] = deepcopy(llm_json[key])
    return plan


def _params_for_dataset(llm_json: dict[str, Any], dataset_key: str) -> dict[str, Any]:
    params_by_dataset = llm_json.get("params_by_dataset")
    if isinstance(params_by_dataset, dict) and isinstance(params_by_dataset.get(dataset_key), dict):
        return deepcopy(params_by_dataset[dataset_key])
    return {}


def _fallback_retrieval_jobs(
    plan: dict[str, Any],
    llm_json: dict[str, Any],
    metadata: dict[str, Any],
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    catalog = ((metadata.get("table_catalog") or {}).get("datasets") or {}) if isinstance(metadata, dict) else {}
    datasets = _unique(plan.get("datasets") or _default_datasets(plan.get("analysis_kind")))
    if not datasets:
        return []
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    question = str(request.get("question") or "")
    request_date = _request_date(payload)
    filters = plan.get("filters") if isinstance(plan.get("filters"), list) else []
    if not filters:
        filters = _infer_filters(question, metadata, plan.get("analysis_kind"), request_date)

    jobs = []
    for index, dataset_key in enumerate(datasets):
        dataset_catalog = catalog.get(dataset_key) if isinstance(catalog.get(dataset_key), dict) else {}
        params = _params_for_dataset(llm_json, dataset_key)
        _fill_required_params(params, dataset_key, dataset_catalog, question, request_date)
        alias = _fallback_alias(plan.get("analysis_kind"), dataset_key, index)
        jobs.append(
            {
                "job_id": f"fallback_{index + 1}_{dataset_key}",
                "dataset_key": dataset_key,
                "source_alias": alias,
                "purpose": _fallback_purpose(plan.get("analysis_kind"), dataset_key),
                "params": params,
                "filters": _filters_for_dataset(filters, dataset_key, dataset_catalog),
                "required_columns": dataset_catalog.get("columns", []),
                "source_type": dataset_catalog.get("source_type", "dummy"),
            }
        )
    return jobs


def _default_datasets(analysis_kind: Any) -> list[str]:
    return {
        "aggregate_join": ["production_today", "wip_today"],
        "aggregate_wip_total": ["wip_today"],
        "date_split_production_plan_gap": ["production", "target"],
        "detail_rows": ["lot_status"],
        "equipment_by_model": ["equipment_status"],
        "equipment_for_previous_products": ["equipment_status"],
        "lot_count_by_process": ["lot_status"],
        "lot_quantity_summary": ["lot_status"],
        "low_output_vs_target": ["production_today", "target"],
        "overall_production_wip_target": ["production_today", "wip_today", "target"],
        "production_wip_target_rate": ["production_today", "wip_today", "target"],
        "rank_top_n": ["wip_today"],
        "rank_wip_then_join_production": ["wip_today", "production_today"],
    }.get(str(analysis_kind or ""), [])


def _fallback_alias(analysis_kind: Any, dataset_key: str, index: int) -> str:
    key = (str(analysis_kind or ""), dataset_key, index)
    aliases = {
        ("aggregate_join", "production_today", 0): "lpddr5_wb_production_today",
        ("aggregate_join", "wip_today", 1): "lpddr5_wb_wip_today",
        ("aggregate_wip_total", "wip_today", 0): "wip_total",
        ("date_split_production_plan_gap", "production", 0): "yesterday_production",
        ("date_split_production_plan_gap", "target", 1): "today_target",
        ("equipment_by_model", "equipment_status", 0): "hbm_equipment_status",
        ("equipment_for_previous_products", "equipment_status", 0): "equipment_for_previous_products",
        ("lot_count_by_process", "lot_status", 0): "lot_count_by_process",
        ("lot_quantity_summary", "lot_status", 0): "da_lot_quantity_summary",
        ("low_output_vs_target", "production_today", 0): "low_output_production",
        ("low_output_vs_target", "target", 1): "low_output_target",
        ("overall_production_wip_target", "production_today", 0): "total_production_today",
        ("overall_production_wip_target", "wip_today", 1): "total_wip_today",
        ("overall_production_wip_target", "target", 2): "total_target",
        ("production_wip_target_rate", "production_today", 0): "scope_production_today",
        ("production_wip_target_rate", "wip_today", 1): "scope_wip_today",
        ("production_wip_target_rate", "target", 2): "scope_target",
        ("rank_top_n", "wip_today", 0): "wip_today_rank",
        ("rank_wip_then_join_production", "wip_today", 0): "wip_today_rank_scope",
        ("rank_wip_then_join_production", "production_today", 1): "production_today_for_ranked_products",
    }
    return aliases.get(key, dataset_key)


def _fallback_purpose(analysis_kind: Any, dataset_key: str) -> str:
    kind = str(analysis_kind or "")
    if kind == "rank_wip_then_join_production" and dataset_key == "wip_today":
        return "rank_source"
    if kind == "rank_wip_then_join_production":
        return "dependent_measure_source"
    if dataset_key in {"production", "production_today"}:
        return "production_source"
    if dataset_key == "wip_today":
        return "wip_source"
    if dataset_key == "target":
        return "plan_source"
    return f"{kind or 'analysis'}_source"


def _fallback_step_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    kind = str(plan.get("analysis_kind") or "")
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    aliases = {job.get("dataset_key"): job.get("source_alias") for job in jobs if isinstance(job, dict)}
    first_alias = jobs[0].get("source_alias") if jobs and isinstance(jobs[0], dict) else ""
    if kind == "aggregate_wip_total":
        return [{"step_id": "sum_wip", "operation": "aggregate_sum", "source_alias": first_alias, "metric": "WIP"}]
    if kind == "rank_top_n":
        return [{"step_id": "rank_top_n", "operation": "rank_top_n", "source_alias": first_alias, "metric": "WIP"}]
    if kind == "detail_rows":
        return [{"step_id": "detail_rows", "operation": "detail_rows", "source_alias": first_alias}]
    if kind == "rank_wip_then_join_production":
        return [
            {"step_id": "rank_products", "operation": "rank_top_n_by_group", "source_alias": aliases.get("wip_today", first_alias), "metric": "WIP"},
            {"step_id": "join_production", "operation": "join_measure_for_ranked_products", "source_alias": aliases.get("production_today", "production_today_for_ranked_products"), "metric": "PRODUCTION"},
        ]
    if kind in {"aggregate_join", "production_wip_target_rate", "low_output_vs_target", "overall_production_wip_target", "date_split_production_plan_gap"}:
        return [{"step_id": f"{kind}_join", "operation": kind, "source_aliases": [job.get("source_alias") for job in jobs]}]
    if kind in {"lot_count_by_process", "lot_quantity_summary", "equipment_for_previous_products", "equipment_by_model"}:
        return [{"step_id": kind, "operation": kind, "source_alias": first_alias}]
    return []


def _fill_required_params(params: dict[str, Any], dataset_key: str, catalog: dict[str, Any], question: str, request_date: str) -> None:
    required = catalog.get("required_params") if isinstance(catalog.get("required_params"), list) else []
    if "DATE" in required and not params.get("DATE"):
        params["DATE"] = _date_param(dataset_key, request_date)
    if "LOT_ID" in required and not params.get("LOT_ID"):
        lot_id = _extract_lot_id(question)
        if lot_id:
            params["LOT_ID"] = lot_id


def _filters_for_dataset(filters: list[Any], dataset_key: str, catalog: dict[str, Any]) -> list[dict[str, Any]]:
    mappings = catalog.get("filter_mappings") if isinstance(catalog.get("filter_mappings"), dict) else {}
    result = []
    for item in filters:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "").strip()
        if not field:
            continue
        if field == "PRODUCT_GRAIN" or field in mappings:
            result.append(deepcopy(item))
    return result


def _infer_filters(question: str, metadata: dict[str, Any], analysis_kind: Any, request_date: str) -> list[dict[str, Any]]:
    text = str(question or "")
    upper = text.upper()
    filters: list[dict[str, Any]] = []
    if "오늘" in text or "현재" in text:
        filters.append({"field": "DATE", "op": "eq", "value": request_date})
    if "LPDDR5" in upper:
        filters.append({"field": "MODE", "op": "eq", "value": "LPDDR5"})
    if "HBM" in upper:
        filters.append({"field": "PKG_TYPE1", "op": "eq", "value": "HBM"})
    if "HOLD" in upper or "홀드" in text:
        filters.append({"field": "LOT_HOLD_STAT_CD", "op": "in", "values": ["HOLD", "OnHold"]})
    if "작업대기" in text:
        filters.append({"field": "LOT_STAT_CD", "op": "in", "values": ["WAITING"]})
    process_values = []
    if _mentions_da(text):
        process_values.extend(_process_values(metadata, "DA"))
    if _mentions_wb(text):
        process_values.extend(_process_values(metadata, "WB"))
    if process_values:
        filters.append({"field": "OPER_NAME", "op": "in", "values": _unique(process_values)})
    if str(analysis_kind or "") == "equipment_for_previous_products":
        filters.append({"field": "PRODUCT_GRAIN", "op": "from_state"})
    return filters


def _attach_state_product_keys(plan: dict[str, Any], payload: dict[str, Any]) -> None:
    if plan.get("state_product_keys"):
        return
    if plan.get("analysis_kind") != "equipment_for_previous_products":
        return
    product_grain = plan.get("product_grain") if isinstance(plan.get("product_grain"), list) else []
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    current_data = state.get("current_data") if isinstance(state.get("current_data"), dict) else {}
    rows = current_data.get("rows") if isinstance(current_data.get("rows"), list) else []
    product_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        product = {key: row.get(key) for key in product_grain if row.get(key) not in {None, ""}}
        if product and product not in product_rows:
            product_rows.append(product)
    if product_rows:
        plan["state_product_keys"] = product_rows


def _process_values(metadata: dict[str, Any], group_key: str) -> list[str]:
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    groups = domain.get("process_groups") if isinstance(domain.get("process_groups"), dict) else {}
    group = groups.get(group_key) if isinstance(groups.get(group_key), dict) else {}
    values = group.get("processes") if isinstance(group.get("processes"), list) else []
    return [str(item) for item in values if str(item or "").strip()]


def _mentions_da(question: str) -> bool:
    upper = str(question or "").upper()
    return "DA" in upper or "D/A" in upper


def _mentions_wb(question: str) -> bool:
    upper = str(question or "").upper()
    return "WB" in upper or "W/B" in upper


def _extract_lot_id(question: str) -> str:
    match = re.search(r"\b[A-Z0-9]{4,}[A-Z0-9_-]*\b", str(question or "").upper())
    return match.group(0) if match else ""


def _request_date(payload: dict[str, Any]) -> str:
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    date_value = str(request.get("date") or request.get("request_date") or "20260612").strip()
    return date_value.replace("-", "")


def _date_param(dataset_key: str, request_date: str) -> str:
    if dataset_key == "target" and len(request_date) == 8:
        return f"{request_date[0:4]}-{request_date[4:6]}-{request_date[6:8]}"
    return request_date


def _route_for_intent(intent_type: Any, job_count: int) -> str:
    text = str(intent_type or "").strip()
    if text == "finish":
        return "finish"
    if text == "followup_transform":
        return "followup_transform"
    if job_count > 1 or text in {"multi_source_analysis", "multi_step_analysis"}:
        return "multi_retrieval"
    return "single_retrieval"


def _metadata_context(intent_plan: dict[str, Any]) -> dict[str, Any]:
    dataset_keys = []
    filter_keys = []
    for job in intent_plan.get("retrieval_jobs", []):
        dataset_key = job.get("dataset_key")
        if dataset_key and dataset_key not in dataset_keys:
            dataset_keys.append(dataset_key)
        for condition in job.get("filters", []):
            if isinstance(condition, dict) and condition.get("field") and condition["field"] not in filter_keys:
                filter_keys.append(condition["field"])
    return {
        "domain_refs": [{"key": "product_grain", "columns": intent_plan.get("product_grain", [])}],
        "table_refs": [{"dataset_key": key} for key in dataset_keys],
        "filter_refs": [{"filter_key": key} for key in filter_keys],
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
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


def _unique(values: Any) -> list[str]:
    result = []
    if not isinstance(values, list):
        values = [values] if values else []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


class IntentPlanNormalizer(Component):
    display_name = "03 Intent Plan Normalizer"
    description = "Normalizes the Gemini/LLM intent JSON into retrieval jobs for the next Langflow nodes."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="llm_response", display_name="LLM Response", required=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        result = normalize_intent_payload(getattr(self, "payload", None), getattr(self, "llm_response", ""))
        plan = result.get("intent_plan", {})
        self.status = {
            "analysis_kind": plan.get("analysis_kind"),
            "jobs": len(plan.get("retrieval_jobs", [])),
            "errors": len(plan.get("normalizer_errors", [])),
        }
        return Data(data=result)
