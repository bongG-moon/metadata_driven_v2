from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


def build_answer_response_payload(payload_value: Any, llm_response_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    data = _build_data(payload, analysis)
    applied_scope = _build_applied_scope(payload)
    answer_message = _answer_text_from_llm(llm_response_value) or _fallback_answer_text(data, applied_scope, analysis)
    state = _next_state(payload, data, applied_scope, answer_message)

    next_payload = dict(payload)
    next_payload.pop("runtime_sources", None)
    next_payload["data"] = data
    next_payload["applied_scope"] = applied_scope
    next_payload["answer_message"] = answer_message
    next_payload["state"] = state
    next_payload["status"] = "ok" if not analysis.get("errors") else "warning"
    next_payload["errors"] = list(payload.get("errors", [])) + list(analysis.get("errors", []))
    return next_payload


def _build_data(payload: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    session_id = ((payload.get("request") or {}).get("session_id") or "demo-session") if isinstance(payload.get("request"), dict) else "demo-session"
    return {
        "columns": list(analysis.get("columns", [])),
        "rows": deepcopy(analysis.get("rows", [])),
        "row_count": int(analysis.get("row_count", 0) or 0),
        "data_ref": f"memory://{session_id}/current_data",
    }


def _build_applied_scope(payload: dict[str, Any]) -> dict[str, Any]:
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    source_results = payload.get("source_results") if isinstance(payload.get("source_results"), list) else []
    filters_by_source = {}
    params_by_source = {}
    datasets = []
    source_aliases = []
    for result in source_results:
        if not isinstance(result, dict):
            continue
        alias = result.get("source_alias")
        dataset_key = result.get("dataset_key")
        if dataset_key:
            datasets.append(dataset_key)
        if alias:
            source_aliases.append(alias)
            filters_by_source[alias] = result.get("applied_filters", [])
            params_by_source[alias] = result.get("applied_params", {})
    return {
        "intent_type": plan.get("intent_type"),
        "analysis_kind": plan.get("analysis_kind"),
        "datasets": _unique(datasets),
        "source_aliases": _unique(source_aliases),
        "step_ids": [step.get("step_id") for step in plan.get("step_plan", []) if isinstance(step, dict)],
        "filters_by_source": filters_by_source,
        "params_by_source": params_by_source,
        "metadata_refs": payload.get("metadata_context", {}),
    }


def _next_state(
    payload: dict[str, Any],
    data: dict[str, Any],
    applied_scope: dict[str, Any],
    answer_message: str,
) -> dict[str, Any]:
    state = deepcopy(payload.get("state", {})) if isinstance(payload.get("state"), dict) else {}
    history = list(state.get("chat_history", [])) if isinstance(state.get("chat_history"), list) else []
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    question = str(request.get("question") or "")
    if question:
        history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer_message})
    state["chat_history"] = history[-10:]
    state["context"] = {
        "last_intent_type": applied_scope.get("intent_type"),
        "last_analysis_kind": applied_scope.get("analysis_kind"),
        "last_datasets": applied_scope.get("datasets", []),
        "last_source_aliases": applied_scope.get("source_aliases", []),
    }
    state["current_data"] = {
        **data,
        "source_dataset_keys": applied_scope.get("datasets", []),
        "source_aliases": applied_scope.get("source_aliases", []),
    }
    state["followup_source_results"] = [
        {
            "source_alias": result.get("source_alias"),
            "dataset_key": result.get("dataset_key"),
            "data_ref": result.get("data_ref"),
            "row_count": result.get("row_count"),
        }
        for result in payload.get("source_results", [])
        if isinstance(result, dict)
    ]
    return state


def _answer_text_from_llm(value: Any) -> str:
    text = _text(value).strip()
    if not text:
        return ""
    parsed = _extract_json_object(text)
    if parsed:
        for key in ("answer_message", "answer", "text", "message"):
            candidate = parsed.get(key)
            if candidate:
                return str(candidate).strip()
    return _strip_markdown_fence(text)


def _fallback_answer_text(data: dict[str, Any], applied_scope: dict[str, Any], analysis: dict[str, Any]) -> str:
    if analysis.get("errors"):
        return "분석 단계에서 확인이 필요합니다. " + "; ".join(str(item) for item in analysis["errors"])
    datasets = ", ".join(applied_scope.get("datasets", []))
    if data["row_count"] == 0:
        return f"조건에 맞는 데이터가 없습니다. 사용 dataset: {datasets}"
    preview = "; ".join(str(row) for row in data["rows"][:2])
    return f"{data['row_count']}건을 찾았습니다. 사용 dataset: {datasets}. 결과 예시: {preview}"


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


def _strip_markdown_fence(text: str) -> str:
    raw = str(text or "").strip()
    fenced = re.match(r"```(?:\w+)?\s*(.*?)\s*```$", raw, re.DOTALL)
    return fenced.group(1).strip() if fenced else raw


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


def _unique(values: list[Any]) -> list[str]:
    result = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


class AnswerResponseBuilder(Component):
    display_name = "10 Answer Response Builder"
    description = "Combines the Langflow Gemini/LLM answer with result data, applied scope, and next-turn state."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="llm_response", display_name="LLM Response", required=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        result = build_answer_response_payload(getattr(self, "payload", None), getattr(self, "llm_response", ""))
        self.status = {
            "status": result.get("status"),
            "rows": (result.get("data") or {}).get("row_count", 0),
            "datasets": (result.get("applied_scope") or {}).get("datasets", []),
        }
        return Data(data=result)
