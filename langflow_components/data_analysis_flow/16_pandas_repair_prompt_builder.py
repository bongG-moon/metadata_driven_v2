from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, DropdownInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


PANDAS_WARNING_PREFIX = "pandas_executor:"
DEFAULT_REPAIR_MAX_ATTEMPTS = 1
REPAIR_ATTEMPT_OPTIONS = ["0", "1", "2"]


def build_pandas_repair_payload(payload_value: Any, max_attempts: Any = DEFAULT_REPAIR_MAX_ATTEMPTS) -> dict[str, Any]:
    payload = _payload(payload_value)
    decision = _pandas_repair_decision(payload, max_attempts)
    next_payload = deepcopy(payload)
    next_payload["pandas_repair"] = decision
    next_payload["pandas_execution_branch"] = {
        "route": decision["route"],
        "repair_required": decision["required"],
        "reason": decision["reason"],
    }
    if decision["required"]:
        next_payload["warnings"] = _without_pandas_executor_warnings(next_payload.get("warnings", []))
        next_payload["pandas_retry_attempt"] = decision["attempt"]
    return next_payload


def build_pandas_repair_prompt_payload(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    repair = payload.get("pandas_repair") if isinstance(payload.get("pandas_repair"), dict) else {}
    if not repair.get("required"):
        prompt = json.dumps(
            {
                "code": "result_df = pd.DataFrame([])",
                "output_columns": [],
                "reasoning_steps": [
                    "No pandas repair is required; downstream repair executor should pass through the previous successful payload."
                ],
            },
            ensure_ascii=False,
        )
        return {
            "prompt": prompt,
            "payload": payload,
            "prompt_type": "pandas_repair_skip",
            "repair_required": False,
            "repair_decision": repair,
        }

    context = repair.get("context") if isinstance(repair.get("context"), dict) else _pandas_repair_context(payload)
    prompt = "\n".join(
        [
            "You repair failed pandas code for a Langflow manufacturing data agent.",
            "Return one strict JSON object only. Do not wrap it in markdown.",
            "Generate corrected Python pandas code that uses only the provided variables: pd, sources, plan, state.",
            "sources is a dict mapping source_alias to pandas DataFrame.",
            "plan and state are Python dicts. Use plan['key'], plan.get('key'), state.get('key'); never use plan.key or state.key.",
            "The code must assign the final pandas DataFrame to result_df.",
            "Do not import modules. Do not read/write files. Do not use network, OS, eval, exec, open, subprocess, numpy, np, or np.where.",
            "Do not use pd.inf, float('inf'), or infinity replacement. Avoid division by zero with boolean masks before dividing.",
            "Fix the failed code using the same intent plan and available source DataFrames. Keep result columns aligned to the requested output contract.",
            "",
            "Failed execution context:",
            json.dumps(context, ensure_ascii=False, indent=2),
            "",
            "Required JSON schema:",
            json.dumps(
                {
                    "code": "Corrected Python code. It must set result_df.",
                    "output_columns": ["column names expected in result_df"],
                    "reasoning_steps": ["short explanation of the repair"],
                },
                ensure_ascii=False,
                indent=2,
            ),
        ]
    )
    return {
        "prompt": prompt,
        "payload": payload,
        "prompt_type": "pandas_code_repair",
        "repair_required": True,
        "repair_decision": repair,
    }


def _pandas_repair_decision(payload: dict[str, Any], max_attempts: Any = DEFAULT_REPAIR_MAX_ATTEMPTS) -> dict[str, Any]:
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    errors = _as_text_list(analysis.get("errors"))
    attempt = _positive_int(payload.get("pandas_retry_attempt"), default=0, minimum=0) + 1
    max_count = _positive_int(max_attempts, default=DEFAULT_REPAIR_MAX_ATTEMPTS, minimum=0)
    required = bool(errors) and attempt <= max_count
    if not errors:
        reason = "pandas 실행이 정상 완료되어 보완 실행이 필요하지 않습니다."
    elif attempt > max_count:
        reason = f"pandas 보완 최대 횟수({max_count})를 초과하여 추가 보완을 실행하지 않습니다."
    else:
        reason = "pandas 실행 오류가 있어 생성 코드와 오류 내용을 기반으로 보완 실행이 필요합니다."
    route = "repair" if required else ("success" if not errors else "failed")
    return {
        "required": required,
        "route": route,
        "attempt": attempt,
        "max_attempts": max_count,
        "errors": errors,
        "reason": reason,
        "context": _pandas_repair_context(payload),
    }


def _pandas_repair_context(payload: dict[str, Any]) -> dict[str, Any]:
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    runtime_sources = payload.get("runtime_sources") if isinstance(payload.get("runtime_sources"), dict) else {}
    return {
        "request": deepcopy(request),
        "intent_plan": deepcopy(payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}),
        "payload_summary": _payload_summary(payload),
        "runtime_source_summary": _runtime_source_summary(runtime_sources),
        "state_summary": _state_summary(state),
        "failed_pandas_code_json": deepcopy(
            analysis.get("pandas_code_json") if isinstance(analysis.get("pandas_code_json"), dict) else {}
        ),
        "executed_code": str(analysis.get("analysis_code") or ""),
        "errors": _as_text_list(analysis.get("errors")),
        "analysis_columns": _as_text_list(analysis.get("columns")),
        "analysis_row_count": analysis.get("row_count", 0),
        "llm_text_preview": str(analysis.get("llm_text_preview") or "")[:1200],
    }


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ("status", "warnings", "errors", "info", "direct_response_ready"):
        if key in payload:
            summary[key] = deepcopy(payload.get(key))
    for key in ("retrieval_jobs", "source_results"):
        value = payload.get(key)
        if isinstance(value, list):
            summary[key] = [_compact_dict(item, 12) for item in value[:20] if isinstance(item, dict)]
    return summary


def _runtime_source_summary(runtime_sources: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
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
    rows = current_data.get("rows") if isinstance(current_data.get("rows"), list) else []
    return {
        "has_state": bool(state),
        "context": deepcopy(state.get("context", {})),
        "current_data_columns": deepcopy(current_data.get("columns", [])),
        "current_data_row_count": current_data.get("row_count", 0),
        "current_data_preview_rows": deepcopy(rows[:3]),
        "current_data_product_key_columns": deepcopy(current_data.get("product_key_columns", [])),
        "current_data_product_key_values": deepcopy(current_data.get("product_key_values", [])[:20])
        if isinstance(current_data.get("product_key_values"), list)
        else [],
    }


def _compact_dict(value: dict[str, Any], max_keys: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for index, (key, item) in enumerate(value.items()):
        if index >= max_keys:
            result["..."] = f"{len(value) - max_keys} more keys"
            break
        if key in {"data", "rows", "runtime_sources"}:
            if isinstance(item, list):
                result[key] = {"row_count": len(item), "preview_rows": deepcopy(item[:3])}
            elif isinstance(item, dict):
                result[key] = {"keys": list(item.keys())[:20]}
            else:
                result[key] = item
        else:
            result[key] = deepcopy(item)
    return result


def _without_pandas_executor_warnings(warnings: Any) -> list[Any]:
    result = []
    for item in warnings if isinstance(warnings, list) else []:
        if str(item).startswith(PANDAS_WARNING_PREFIX):
            continue
        result.append(item)
    return result


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    return [str(item) for item in value if str(item or "").strip()]


def _positive_int(value: Any, default: int, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, parsed)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


class PandasRepairPromptBuilder(Component):
    display_name = "16 Pandas Repair Prompt Builder"
    description = "Decides whether failed pandas execution needs LLM repair and builds the repair prompt."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        DropdownInput(
            name="max_attempts",
            display_name="Max Repair Attempts",
            options=REPAIR_ATTEMPT_OPTIONS,
            value=str(DEFAULT_REPAIR_MAX_ATTEMPTS),
            advanced=True,
        ),
    ]
    outputs = [
        Output(
            name="payload_out",
            display_name="Repair Payload",
            method="build_payload",
            group_outputs=True,
            types=["Data"],
        ),
        Output(
            name="repair_prompt",
            display_name="Repair Prompt",
            method="build_repair_prompt",
            group_outputs=True,
            types=["Message"],
        ),
        Output(
            name="repair_decision",
            display_name="Repair Decision",
            method="build_repair_decision",
            group_outputs=True,
            types=["Data"],
        ),
    ]

    def build_payload(self) -> Data:
        return Data(data=self._result())

    def build_repair_prompt(self) -> Message:
        prompt_payload = build_pandas_repair_prompt_payload(self._result())
        return Message(text=prompt_payload["prompt"])

    def build_repair_decision(self) -> Data:
        result = self._result()
        return Data(
            data={
                "pandas_repair": result.get("pandas_repair", {}),
                "pandas_execution_branch": result.get("pandas_execution_branch", {}),
            }
        )

    def _result(self) -> dict[str, Any]:
        cached = getattr(self, "_cached_result", None)
        if isinstance(cached, dict):
            return cached
        result = build_pandas_repair_payload(getattr(self, "payload", None), getattr(self, "max_attempts", DEFAULT_REPAIR_MAX_ATTEMPTS))
        self._cached_result = result
        self._set_status(result)
        return result

    def _set_status(self, result: dict[str, Any]) -> None:
        repair = result.get("pandas_repair") if isinstance(result.get("pandas_repair"), dict) else {}
        self.status = {
            "route": repair.get("route", ""),
            "repair_required": repair.get("required", False),
            "attempt": repair.get("attempt", 0),
            "max_attempts": repair.get("max_attempts", DEFAULT_REPAIR_MAX_ATTEMPTS),
            "errors": len(repair.get("errors", [])),
        }
