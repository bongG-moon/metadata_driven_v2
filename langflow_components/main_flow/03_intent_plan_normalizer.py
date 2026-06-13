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
            notes.append("retrieval_jobs were missing; built fallback jobs only from LLM-provided datasets, metadata, and request context.")
        else:
            errors.append("No retrieval_jobs were provided and no LLM-provided datasets were available for generic fallback job generation.")
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
        if "primary_quantity_column" not in job and dataset_catalog.get("primary_quantity_column"):
            job["primary_quantity_column"] = deepcopy(dataset_catalog["primary_quantity_column"])
        normalized_jobs.append(job)
    plan["retrieval_jobs"] = normalized_jobs
    plan["datasets"] = _unique([job["dataset_key"] for job in normalized_jobs] or llm_json.get("datasets", []))
    if not plan.get("step_plan"):
        fallback_steps = _fallback_step_plan(plan, metadata, payload)
        if fallback_steps:
            plan["step_plan"] = fallback_steps
            notes.append("step_plan was missing; built a minimal generic fallback step_plan from retrieval aliases.")
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
        "metric",
        "rank_order",
        "threshold",
        "threshold_percent",
        "top_n",
        "bottom_n",
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
    datasets = _unique(plan.get("datasets"))
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
        alias = _fallback_alias(plan, dataset_key, index, len(datasets))
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
                "primary_quantity_column": deepcopy(dataset_catalog.get("primary_quantity_column")),
            }
        )
    return jobs


def _fallback_alias(plan: dict[str, Any], dataset_key: str, index: int, dataset_count: int) -> str:
    if dataset_count == 1:
        step_plan = plan.get("step_plan") if isinstance(plan.get("step_plan"), list) else []
        for step in step_plan:
            if isinstance(step, dict) and step.get("source_alias"):
                return str(step["source_alias"])
        return dataset_key
    return f"{dataset_key}_{index + 1}"


def _fallback_purpose(analysis_kind: Any, dataset_key: str) -> str:
    kind = str(analysis_kind or "")
    return f"{kind or 'analysis'}_source:{dataset_key}"


def _fallback_step_plan(plan: dict[str, Any], metadata: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    kind = str(plan.get("analysis_kind") or "")
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    first_alias = jobs[0].get("source_alias") if jobs and isinstance(jobs[0], dict) else ""
    if kind in {"rank_top_n", "rank_bottom_n"} and first_alias:
        return [
            {
                "step_id": "rank_items",
                "operation": kind,
                "source_alias": first_alias,
                "metric": _fallback_metric(plan, jobs[0], metadata),
                "top_n": _fallback_rank_n(plan, payload),
                "rank_order": _fallback_rank_order(plan, payload, kind),
            }
        ]
    if kind == "detail_rows" and first_alias:
        return [{"step_id": "detail_rows", "operation": "detail_rows", "source_alias": first_alias}]
    return []


def _fallback_metric(plan: dict[str, Any], job: dict[str, Any], metadata: dict[str, Any]) -> str:
    for key in ("metric", "target_column"):
        value = plan.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    quantity = job.get("primary_quantity_column")
    if isinstance(quantity, str) and quantity.strip():
        return quantity.strip()
    if isinstance(quantity, list):
        for item in quantity:
            text = str(item or "").strip()
            if text:
                return text
    catalog = ((metadata.get("table_catalog") or {}).get("datasets") or {}) if isinstance(metadata, dict) else {}
    dataset_key = str(job.get("dataset_key") or "")
    dataset_catalog = catalog.get(dataset_key) if isinstance(catalog.get(dataset_key), dict) else {}
    quantity = dataset_catalog.get("primary_quantity_column")
    if isinstance(quantity, str) and quantity.strip():
        return quantity.strip()
    if isinstance(quantity, list):
        for item in quantity:
            text = str(item or "").strip()
            if text:
                return text
    return ""


def _fallback_rank_n(plan: dict[str, Any], payload: dict[str, Any]) -> int:
    for key in ("top_n", "bottom_n"):
        value = plan.get(key)
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit() and int(value) > 0:
            return int(value)
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    question = str(request.get("question") or "")
    match = re.search(r"\b(\d{1,2})\b", question)
    if match:
        return int(match.group(1))
    return 5


def _fallback_rank_order(plan: dict[str, Any], payload: dict[str, Any], kind: str) -> str:
    order = str(plan.get("rank_order") or "").strip().lower()
    if order in {"asc", "ascending"}:
        return "asc"
    if order in {"desc", "descending"}:
        return "desc"
    question = ""
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    if isinstance(request, dict):
        question = str(request.get("question") or "")
    text = question.lower()
    if kind == "rank_bottom_n" or "bottom" in text or "lowest" in text or "하위" in question or "낮은" in question:
        return "asc"
    return "desc"


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
    filters: list[dict[str, Any]] = []
    if _mentions_any(text, ["오늘", "현재", "today", "current"]) and _metadata_has_filter(metadata, "DATE"):
        filters.append({"field": "DATE", "op": "eq", "value": request_date})
    filters.extend(_metadata_term_filters(text, metadata))
    process_values = _metadata_process_values(text, metadata)
    if process_values and _metadata_has_filter(metadata, "OPER_NAME"):
        filters.append({"field": "OPER_NAME", "op": "in", "values": _unique(process_values)})
    if str(analysis_kind or "") == "equipment_for_previous_products":
        filters.append({"field": "PRODUCT_GRAIN", "op": "from_state"})
    return _dedupe_filters(filters)


def _attach_state_product_keys(plan: dict[str, Any], payload: dict[str, Any]) -> None:
    if plan.get("state_product_keys"):
        return
    if plan.get("analysis_kind") != "equipment_for_previous_products":
        return
    product_grain = plan.get("product_grain") if isinstance(plan.get("product_grain"), list) else []
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    current_data = state.get("current_data") if isinstance(state.get("current_data"), dict) else {}
    rows = _rows_from_current_data(current_data)
    product_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        product = {key: row.get(key) for key in product_grain if row.get(key) not in {None, ""}}
        if product and product not in product_rows:
            product_rows.append(product)
    if product_rows:
        plan["state_product_keys"] = product_rows


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


def _metadata_term_filters(question: str, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    result: list[dict[str, Any]] = []
    for section_name in ("product_terms", "status_terms"):
        terms = domain.get(section_name) if isinstance(domain.get(section_name), dict) else {}
        for term_key, term in terms.items():
            if not isinstance(term, dict):
                continue
            aliases = term.get("aliases") if isinstance(term.get("aliases"), list) else []
            match_values = [term_key, term.get("display_name"), *aliases]
            if not _mentions_any(question, match_values):
                continue
            condition = term.get("condition") if isinstance(term.get("condition"), dict) else {}
            result.extend(_condition_to_filters(condition, metadata))
    return result


def _metadata_process_values(question: str, metadata: dict[str, Any]) -> list[str]:
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    groups = domain.get("process_groups") if isinstance(domain.get("process_groups"), dict) else {}
    result: list[str] = []
    for group_key, group in groups.items():
        if not isinstance(group, dict):
            continue
        aliases = group.get("aliases") if isinstance(group.get("aliases"), list) else []
        match_values = [group_key, group.get("display_name"), *aliases]
        if not _mentions_any(question, match_values):
            continue
        values = group.get("processes") if isinstance(group.get("processes"), list) else []
        result.extend(str(item) for item in values if str(item or "").strip())
    return _unique(result)


def _condition_to_filters(condition: dict[str, Any], metadata: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for field, spec in condition.items():
        field_name = str(field or "").strip()
        if not field_name or not _metadata_has_filter(metadata, field_name):
            continue
        if isinstance(spec, dict):
            if spec.get("exists") and spec.get("not_in"):
                result.append({"field": field_name, "op": "not_empty"})
            elif spec.get("exists"):
                result.append({"field": field_name, "op": "not_empty"})
            elif isinstance(spec.get("in"), list):
                result.append({"field": field_name, "op": "in", "values": deepcopy(spec["in"])})
            elif "value" in spec:
                result.append({"field": field_name, "op": "eq", "value": spec.get("value")})
        elif isinstance(spec, list):
            result.append({"field": field_name, "op": "in", "values": deepcopy(spec)})
        else:
            result.append({"field": field_name, "op": "eq", "value": spec})
    return result


def _metadata_has_filter(metadata: dict[str, Any], filter_key: str) -> bool:
    filters = metadata.get("main_flow_filters") if isinstance(metadata.get("main_flow_filters"), dict) else {}
    return str(filter_key or "") in filters


def _dedupe_filters(filters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in filters:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _mentions_any(question: str, aliases: list[Any]) -> bool:
    return any(_alias_in_text(question, alias) for alias in aliases)


def _alias_in_text(question: str, alias: Any) -> bool:
    text = str(question or "")
    value = str(alias or "").strip()
    if not value:
        return False
    if re.fullmatch(r"[A-Za-z0-9/.-]{1,4}", value):
        pattern = r"(?<![A-Za-z0-9])" + re.escape(value) + r"(?![A-Za-z0-9])"
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
    return value in text or value.upper() in text.upper()


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
