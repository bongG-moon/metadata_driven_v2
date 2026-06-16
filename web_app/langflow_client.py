from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Iterable

import requests


DEFAULT_COLLECTIONS = {
    "domain": "agent_v2_domain_items",
    "table_catalog": "agent_v2_table_catalog_items",
    "main_flow_filter": "agent_v2_main_flow_filters",
}


@dataclass(frozen=True)
class LangflowSettings:
    api_key: str = ""
    main_api_url: str = ""
    domain_authoring_api_url: str = ""
    table_catalog_authoring_api_url: str = ""
    main_flow_filter_authoring_api_url: str = ""
    input_type: str = "chat"
    output_type: str = "chat"
    timeout: int = 180

    @classmethod
    def from_env(cls) -> "LangflowSettings":
        base_url = _env("LANGFLOW_BASE_URL") or _env("LANGFLOW_API_BASE_URL")
        return cls(
            api_key=_env("LANGFLOW_API_KEY"),
            main_api_url=_env("LANGFLOW_MAIN_API_URL") or _env("LANGFLOW_API_URL") or _flow_run_url(base_url, _env("LANGFLOW_MAIN_FLOW_ID")),
            domain_authoring_api_url=_env("LANGFLOW_DOMAIN_AUTHORING_API_URL") or _flow_run_url(base_url, _env("LANGFLOW_DOMAIN_AUTHORING_FLOW_ID")),
            table_catalog_authoring_api_url=_env("LANGFLOW_TABLE_CATALOG_AUTHORING_API_URL")
            or _flow_run_url(base_url, _env("LANGFLOW_TABLE_CATALOG_AUTHORING_FLOW_ID")),
            main_flow_filter_authoring_api_url=_env("LANGFLOW_MAIN_FILTER_AUTHORING_API_URL")
            or _env("LANGFLOW_MAIN_FLOW_FILTER_AUTHORING_API_URL")
            or _flow_run_url(base_url, _env("LANGFLOW_MAIN_FILTER_AUTHORING_FLOW_ID")),
            input_type=_env("LANGFLOW_INPUT_TYPE") or "chat",
            output_type=_env("LANGFLOW_OUTPUT_TYPE") or "chat",
            timeout=_int_env("LANGFLOW_TIMEOUT_SECONDS", 180),
        )

    def authoring_url(self, metadata_type: str) -> str:
        kind = normalize_metadata_type(metadata_type)
        return {
            "domain": self.domain_authoring_api_url,
            "table_catalog": self.table_catalog_authoring_api_url,
            "main_flow_filter": self.main_flow_filter_authoring_api_url,
        }[kind]

    def configured_summary(self) -> dict[str, bool]:
        return {
            "main": bool(self.main_api_url),
            "domain": bool(self.domain_authoring_api_url),
            "table_catalog": bool(self.table_catalog_authoring_api_url),
            "main_flow_filter": bool(self.main_flow_filter_authoring_api_url),
        }


class LangflowApiClient:
    def __init__(self, settings: LangflowSettings | None = None) -> None:
        self.settings = settings or LangflowSettings.from_env()

    def run_query(self, question: str, session_id: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.settings.main_api_url:
            raise ValueError("LANGFLOW_MAIN_API_URL 또는 LANGFLOW_MAIN_FLOW_ID가 설정되지 않았습니다.")
        raw_response = call_langflow_api(
            self.settings.main_api_url,
            api_key=self.settings.api_key,
            input_value=question,
            session_id=session_id,
            input_type=self.settings.input_type,
            output_type=self.settings.output_type,
            tweaks=build_main_flow_tweaks(state, session_id),
            timeout=self.settings.timeout,
        )
        result = normalize_query_response(raw_response)
        result["api_mode"] = "langflow_api"
        result["raw_response"] = raw_response
        return result

    def run_authoring(self, metadata_type: str, raw_text: str, duplicate_action: str, session_id: str) -> dict[str, Any]:
        kind = normalize_metadata_type(metadata_type)
        api_url = self.settings.authoring_url(kind)
        if not api_url:
            raise ValueError(f"{kind} authoring API URL 또는 flow id가 설정되지 않았습니다.")
        raw_response = call_langflow_api(
            api_url,
            api_key=self.settings.api_key,
            input_value=raw_text,
            session_id=session_id,
            input_type=self.settings.input_type,
            output_type=self.settings.output_type,
            tweaks=build_authoring_tweaks(kind, duplicate_action),
            timeout=self.settings.timeout,
        )
        result = normalize_authoring_response(raw_response)
        result["metadata_type"] = result.get("metadata_type") or kind
        result["api_mode"] = "langflow_api"
        result["raw_response"] = raw_response
        return result


def call_langflow_api(
    api_url: str,
    api_key: str,
    input_value: str,
    session_id: str,
    input_type: str = "chat",
    output_type: str = "chat",
    tweaks: dict[str, Any] | None = None,
    timeout: int = 180,
) -> dict[str, Any]:
    if not str(api_url or "").strip():
        raise ValueError("Langflow API URL is not configured.")
    if not str(input_value or "").strip():
        raise ValueError("input_value is empty.")
    payload: dict[str, Any] = {
        "output_type": output_type or "chat",
        "input_type": input_type or "chat",
        "input_value": input_value,
        "session_id": session_id,
    }
    if tweaks:
        payload["tweaks"] = tweaks
    headers = {"Content-Type": "application/json"}
    if str(api_key or "").strip():
        headers["x-api-key"] = str(api_key).strip()
    response = requests.post(api_url, json=payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    parsed = response.json()
    return parsed if isinstance(parsed, dict) else {"response": parsed}


def build_main_flow_tweaks(state: dict[str, Any] | None, session_id: str) -> dict[str, Any] | None:
    if not state:
        return None
    return {
        "00 Request State Loader": {
            "session_id": session_id,
            "state": state,
        }
    }


def build_authoring_tweaks(metadata_type: str, duplicate_action: str) -> dict[str, Any]:
    kind = normalize_metadata_type(metadata_type)
    action = normalize_duplicate_action(duplicate_action)
    collection_name = _collection_name(kind)
    labels = {
        "domain": ["00 Domain Authoring Request Loader", "05 Domain Similarity Checker", "07 Domain Review Writer"],
        "table_catalog": ["00 Table Catalog Authoring Request Loader", "05 Table Catalog Similarity Checker", "07 Table Catalog Review Writer"],
        "main_flow_filter": [
            "00 Main Flow Filter Authoring Request Loader",
            "05 Main Flow Filter Similarity Checker",
            "07 Main Flow Filter Review Writer",
        ],
    }[kind]
    tweaks: dict[str, Any] = {}
    for label in labels:
        tweaks[label] = {"duplicate_action": action}
        if label.startswith("00 ") or label.startswith("07 "):
            tweaks[label]["collection_name"] = collection_name
    return tweaks


def normalize_query_response(api_response: Any) -> dict[str, Any]:
    payload = extract_main_payload(api_response)
    data = _query_data(payload)
    applied_scope = _as_dict(payload.get("applied_scope") or payload.get("scope"))
    intent_plan = _as_dict(payload.get("intent_plan"))
    intent = _as_dict(payload.get("intent"))
    analysis = _query_analysis(payload, data)
    warnings = _unique_values([*_as_list(payload.get("warnings")), *_as_list(analysis.get("warnings"))])
    errors = _unique_values([*_as_list(payload.get("errors")), *_as_list(analysis.get("errors"))])
    answer = _first_text(payload, ["answer_message", "message", "response", "answer", "text", "content"])
    if not answer:
        answer = "응답 텍스트를 찾지 못했습니다. Raw payload를 확인하세요."
    metadata_qa = _as_dict(payload.get("metadata_qa"))
    metadata_route = _as_dict(payload.get("metadata_route"))
    direct_response_ready = bool(payload.get("direct_response_ready") or metadata_qa)

    result = {
        "status": str(payload.get("status") or analysis.get("status") or ("error" if errors else "ok")),
        "success": bool(payload.get("success", not errors)),
        "response_type": str(payload.get("response_type") or ("metadata_qa" if direct_response_ready else "analysis")),
        "direct_response_ready": direct_response_ready,
        "answer_message": answer,
        "message": answer,
        "data": data,
        "applied_scope": applied_scope,
        "intent_plan": intent_plan or intent,
        "intent": intent,
        "metadata_qa": metadata_qa,
        "metadata_route": metadata_route,
        "analysis": analysis,
        "state": _as_dict(payload.get("state")),
        "warnings": warnings,
        "errors": errors,
        "data_refs": _collect_data_refs(payload, data),
        "developer": _as_dict(payload.get("developer") or payload.get("debug")),
    }
    if result["developer"] and not result["analysis"].get("analysis_code"):
        code = result["developer"].get("analysis_code") or _as_dict(result["developer"].get("pandas_code_json")).get("code")
        if code:
            result["analysis"]["analysis_code"] = code
    return result


def normalize_authoring_response(api_response: Any) -> dict[str, Any]:
    payload = extract_authoring_payload(api_response)
    kind = normalize_metadata_type(payload.get("metadata_type") or payload.get("flow_type"))
    review = _as_dict(payload.get("review") or payload.get("review_result"))
    write_result = _as_dict(payload.get("write_result"))
    trace = _normalize_authoring_trace(payload)
    errors = _unique_values([*_as_list(payload.get("errors")), *_trace_values(trace, "errors")])
    warnings = _unique_values([*_as_list(payload.get("warnings")), *_trace_values(trace, "warnings")])
    existing_matches = _as_list(payload.get("existing_matches"))
    conflict_warnings = _as_list(payload.get("conflict_warnings")) or warnings
    ui_status = _authoring_ui_status(payload, review, write_result, trace, existing_matches, conflict_warnings, errors)
    return {
        "status": str(payload.get("status") or write_result.get("status") or ui_status),
        "ui_status": ui_status,
        "message": _first_text(payload, ["message", "response", "answer_message"]) or _authoring_message(ui_status, write_result, review),
        "metadata_type": kind,
        "items": [item for item in _as_list(payload.get("items")) if isinstance(item, dict)],
        "existing_matches": existing_matches,
        "conflict_warnings": conflict_warnings,
        "review": review,
        "write_result": write_result,
        "trace": trace,
        "errors": errors,
        "warnings": warnings,
        "api_response": payload,
    }


def extract_main_payload(value: Any) -> dict[str, Any]:
    for item in _walk(value):
        item = _parse_json_dict(item) if isinstance(item, str) else item
        if not isinstance(item, dict):
            continue
        api_payload = item.get("api_response")
        if isinstance(api_payload, dict) and _looks_like_query(api_payload):
            return dict(api_payload)
        if _looks_like_query(item):
            return dict(item)
    return _as_dict(value)


def extract_authoring_payload(value: Any) -> dict[str, Any]:
    for item in _walk(value):
        item = _parse_json_dict(item) if isinstance(item, str) else item
        if not isinstance(item, dict):
            continue
        api_payload = item.get("api_response")
        if isinstance(api_payload, dict) and _looks_like_authoring(api_payload):
            return dict(api_payload)
        if _looks_like_authoring(item):
            return dict(item)
    return _as_dict(value)


def normalize_metadata_type(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    if text in {"domain", "domains"}:
        return "domain"
    if text in {"table", "table_catalog", "catalog", "data_catalog"}:
        return "table_catalog"
    return "main_flow_filter"


def normalize_duplicate_action(value: Any) -> str:
    text = str(value or "ask").strip().lower()
    return text if text in {"ask", "merge", "replace", "skip", "create_new"} else "ask"


def _query_data(payload: dict[str, Any]) -> dict[str, Any]:
    data_value = payload.get("data")
    if isinstance(data_value, dict):
        data_source = data_value
        rows = _row_list(data_source.get("rows"))
    else:
        data_source = {}
        rows = _row_list(data_value)
    final_data = _as_dict(payload.get("final_data"))
    analysis = _as_dict(payload.get("analysis") or payload.get("analysis_result"))
    if not rows:
        rows = _row_list(final_data.get("rows")) or _row_list(analysis.get("rows")) or _row_list(analysis.get("data"))
    columns = (
        _string_list(data_source.get("columns"))
        or _string_list(payload.get("columns"))
        or _string_list(final_data.get("columns"))
        or _string_list(analysis.get("columns"))
        or _columns_from_rows(rows)
    )
    row_count = _int_value(data_source.get("row_count"), _int_value(payload.get("row_count"), _int_value(final_data.get("row_count"), len(rows))))
    data_ref = _normalize_data_ref(data_source.get("data_ref") or payload.get("data_ref") or final_data.get("data_ref") or analysis.get("data_ref"))
    result = {
        "columns": columns,
        "rows": rows,
        "row_count": row_count,
        "data_ref": data_ref,
    }
    for key in ("data_is_preview", "data_is_reference", "rows_are_preview", "data_ref_loaded", "data_ref_load_mode"):
        value = data_source.get(key) if isinstance(data_source, dict) else None
        if value in (None, "", [], {}):
            value = payload.get(key) or analysis.get(key)
        if value not in (None, "", [], {}):
            result[key] = value
    if "data_is_preview" not in result and row_count > len(rows):
        result["data_is_preview"] = True
    return result


def _query_analysis(payload: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    source = _as_dict(payload.get("analysis") or payload.get("analysis_result"))
    developer = _as_dict(payload.get("developer") or payload.get("debug"))
    pandas_code_json = _as_dict(source.get("pandas_code_json")) or _as_dict(developer.get("pandas_code_json"))
    analysis_code = source.get("analysis_code") or developer.get("analysis_code") or pandas_code_json.get("code") or payload.get("analysis_code")
    result = {
        "status": source.get("status") or payload.get("analysis_status") or developer.get("analysis_status"),
        "safety_passed": source.get("safety_passed"),
        "executed": source.get("executed"),
        "columns": _string_list(source.get("columns")) or list(data.get("columns") or []),
        "rows": _row_list(source.get("rows")),
        "row_count": _int_value(source.get("row_count"), int(data.get("row_count") or 0)),
        "analysis_code": analysis_code or "",
        "pandas_code_json": pandas_code_json,
        "reasoning_steps": _as_list(source.get("reasoning_steps") or developer.get("reasoning_steps")),
        "warnings": _as_list(source.get("warnings")),
        "errors": _as_list(source.get("errors")),
    }
    return {key: value for key, value in result.items() if value not in (None, "", [], {})}


def _collect_data_refs(payload: dict[str, Any], data: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref in _as_list(payload.get("data_refs")):
        _append_data_ref(refs, ref)
    _append_data_ref(refs, data.get("data_ref"))
    developer = _as_dict(payload.get("developer") or payload.get("debug"))
    for ref in _as_list(developer.get("data_refs")):
        _append_data_ref(refs, ref)
    return refs


def _normalize_authoring_trace(payload: dict[str, Any]) -> dict[str, Any]:
    trace = payload.get("trace")
    if isinstance(trace, dict):
        return dict(trace)
    stages = [dict(item) for item in trace if isinstance(item, dict)] if isinstance(trace, list) else []
    return {
        "raw_text": payload.get("raw_text") or payload.get("user_input") or _stage_text(stages, "input", "raw_text"),
        "refined_text": payload.get("refined_text") or _stage_text(stages, "refinement", "refined_text"),
        "duplicate_decision": _as_dict(payload.get("duplicate_decision")),
        "stages": stages,
    }


def _authoring_ui_status(
    payload: dict[str, Any],
    review: dict[str, Any],
    write_result: dict[str, Any],
    trace: dict[str, Any],
    existing_matches: list[Any],
    conflict_warnings: list[Any],
    errors: list[Any],
) -> str:
    status = str(write_result.get("status") or payload.get("status") or "").lower()
    duplicate_decision = _as_dict(trace.get("duplicate_decision"))
    supplement = _as_list(review.get("supplement_requests"))
    if errors or status == "error":
        return "error"
    if supplement or review.get("needs_supplement") or payload.get("needs_supplement"):
        return "needs_more_input"
    if existing_matches or duplicate_decision.get("requires_user_choice"):
        return "duplicate_choice_required"
    if status == "skipped" or write_result.get("skipped"):
        return "skipped"
    if status == "ok" or write_result.get("success") or int(write_result.get("saved_count") or 0) > 0:
        return "saved"
    if conflict_warnings:
        return "warning"
    return str(payload.get("status") or "processed")


def _authoring_message(ui_status: str, write_result: dict[str, Any], review: dict[str, Any]) -> str:
    if ui_status == "saved":
        return f"{int(write_result.get('saved_count') or 0)}개 metadata item을 저장했습니다."
    if ui_status == "needs_more_input":
        return "저장 전에 추가 정보가 필요합니다."
    if ui_status == "duplicate_choice_required":
        return "비슷한 기존 metadata가 있어 저장 방식을 선택해야 합니다."
    if ui_status == "error":
        return "처리 중 오류가 발생했습니다."
    if review:
        return "검토 결과를 확인하세요."
    return "처리 결과를 확인하세요."


def _looks_like_query(value: dict[str, Any]) -> bool:
    if _looks_like_authoring(value):
        return False
    return any(
        key in value
        for key in (
            "answer_message",
            "applied_scope",
            "intent_plan",
            "analysis",
            "data_ref",
            "data_refs",
            "direct_response_ready",
            "metadata_qa",
            "metadata_route",
        )
    ) or (
        "response" in value and any(key in value for key in ("data", "columns", "row_count"))
    )


def _looks_like_authoring(value: dict[str, Any]) -> bool:
    return any(key in value for key in ("metadata_type", "review", "review_result", "write_result", "existing_matches")) and any(
        key in value for key in ("items", "trace", "status", "message")
    )


def _walk(value: Any) -> Iterable[Any]:
    parsed = _parse_json_dict(value) if isinstance(value, str) else None
    if parsed:
        yield parsed
        for child in parsed.values():
            yield from _walk(child)
        yield value
        return
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _parse_json_dict(value: str) -> dict[str, Any] | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidates = [text]
    if text.lower().startswith("json"):
        candidates.append(text[4:].lstrip(" \t\r\n:"))
    if text.startswith("```"):
        lines = text.splitlines()
        body = "\n".join(lines[1:])
        if body.rstrip().endswith("```"):
            body = body.rstrip()[:-3].strip()
        candidates.append(body)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _append_data_ref(refs: list[dict[str, Any]], ref: Any) -> None:
    normalized = _normalize_data_ref(ref)
    if not normalized:
        return
    signature = "|".join(str(normalized.get(key) or "") for key in ("ref_id", "path", "collection_name", "store"))
    for existing in refs:
        existing_signature = "|".join(str(existing.get(key) or "") for key in ("ref_id", "path", "collection_name", "store"))
        if existing_signature == signature:
            return
    refs.append(normalized)


def _normalize_data_ref(ref: Any) -> dict[str, Any]:
    if isinstance(ref, dict) and ref:
        return dict(ref)
    if isinstance(ref, str) and ref.strip():
        text = ref.strip()
        return {"store": "memory" if text.startswith("memory://") else "external", "ref_id": text}
    return {}


def _stage_text(stages: list[dict[str, Any]], stage_name: str, key: str) -> str:
    for stage in stages:
        if stage.get("stage") == stage_name and isinstance(stage.get(key), str):
            return str(stage.get(key) or "")
    return ""


def _trace_values(trace: dict[str, Any], key: str) -> list[Any]:
    values: list[Any] = []
    for stage in _as_list(trace.get("stages")):
        if isinstance(stage, dict):
            values.extend(_as_list(stage.get(key)))
    return values


def _collection_name(metadata_type: str) -> str:
    kind = normalize_metadata_type(metadata_type)
    env_names = {
        "domain": ["MONGODB_DOMAIN_COLLECTION", "DOMAIN_COLLECTION_NAME"],
        "table_catalog": ["MONGODB_TABLE_CATALOG_COLLECTION", "TABLE_CATALOG_COLLECTION_NAME"],
        "main_flow_filter": ["MONGODB_MAIN_FLOW_FILTER_COLLECTION", "MAIN_FLOW_FILTER_COLLECTION_NAME"],
    }[kind]
    for name in env_names:
        value = _env(name)
        if value:
            return value
    return DEFAULT_COLLECTIONS[kind]


def _env(name: str) -> str:
    return str(os.getenv(name, "") or "").strip()


def _flow_run_url(base_url: str, flow_id: str) -> str:
    if not base_url or not flow_id:
        return ""
    return f"{base_url.rstrip('/')}/api/v1/run/{flow_id.strip()}"


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except Exception:
        return default


def _first_text(payload: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple, set)) else []


def _row_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(row) for row in value if isinstance(row, dict)]


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in _as_list(value) if str(item or "").strip()]


def _columns_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(str(key))
    return columns


def _int_value(value: Any, fallback: int = 0) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == value:
        return int(value)
    try:
        return int(str(value))
    except Exception:
        return fallback


def _unique_values(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    signatures: set[str] = set()
    for value in values:
        if value in (None, "", [], {}):
            continue
        try:
            signature = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            signature = str(value)
        if signature in signatures:
            continue
        signatures.add(signature)
        result.append(value)
    return result
