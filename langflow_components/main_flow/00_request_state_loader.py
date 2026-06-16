from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


DEFAULT_STATE_PREVIEW_LIMIT = 5


def build_request_payload(question: str, session_id: str = "demo-session", state: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "payload_version": "agent-v1",
        "status": "ok",
        "request": {"session_id": session_id, "question": question, "timezone": "Asia/Seoul"},
        "state": _compact_previous_state(state),
        "info": [],
        "warnings": [],
        "errors": [],
    }


def _compact_previous_state(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        state = {}
    result = deepcopy(state)
    result["chat_history"] = list(result.get("chat_history", [])) if isinstance(result.get("chat_history"), list) else []
    result["context"] = dict(result.get("context", {})) if isinstance(result.get("context"), dict) else {}
    result["current_data"] = _compact_current_data(result.get("current_data"))
    if not isinstance(result.get("followup_source_results"), list):
        result["followup_source_results"] = []
    return result


def _compact_current_data(current_data: Any, preview_limit: int = DEFAULT_STATE_PREVIEW_LIMIT) -> dict[str, Any]:
    if not isinstance(current_data, dict):
        return {}
    result = deepcopy(current_data)
    rows = _rows_from_current_data(result)
    row_count = _positive_int(result.get("row_count"), default=len(rows))
    if rows:
        result["rows"] = deepcopy(rows[:preview_limit])
        result.pop("data", None)
    result["row_count"] = row_count
    columns = result.get("columns") if isinstance(result.get("columns"), list) else []
    if not columns:
        columns = _rows_columns(rows)
    result["columns"] = columns
    if rows:
        result["data_is_preview"] = row_count > len(result["rows"])
        result.setdefault("data_ref_loaded", False)
        if isinstance(result.get("data_ref"), dict):
            result.setdefault("data_ref_load_mode", "preview")

    product_key_columns = [str(item) for item in result.get("product_key_columns", []) if str(item or "").strip()] if isinstance(result.get("product_key_columns"), list) else []
    result["product_key_columns"] = product_key_columns
    product_key_values = result.get("product_key_values") if isinstance(result.get("product_key_values"), list) else []
    if not product_key_values and product_key_columns:
        product_key_values = _product_key_values(rows, product_key_columns)
    result["product_key_values"] = deepcopy(product_key_values)
    result["product_key_count"] = _positive_int(result.get("product_key_count"), default=len(product_key_values))
    if not isinstance(result.get("source_dataset_keys"), list):
        result["source_dataset_keys"] = []
    if not isinstance(result.get("source_aliases"), list):
        result["source_aliases"] = []
    return result


def _rows_from_current_data(current_data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = current_data.get("rows")
    if not isinstance(rows, list):
        rows = current_data.get("data")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _rows_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            text = str(key)
            if text not in columns:
                columns.append(text)
    return columns


def _product_key_values(rows: list[dict[str, Any]], product_key_columns: list[str]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for row in rows:
        product = {key: row.get(key) for key in product_key_columns if row.get(key) not in {None, ""}}
        if product and product not in values:
            values.append(product)
    return values


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(0, parsed)



class RequestStateLoader(Component):
    display_name = "00 Request State Loader"
    description = "Builds the compact request payload from chat input and previous state."
    inputs = [
        MessageTextInput(name="question", display_name="Question", required=True),
        MessageTextInput(name="session_id", display_name="Session ID", value="demo-session"),
        DataInput(name="state", display_name="Previous State", required=False),
    ]
    outputs = [Output(name="payload", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        state = getattr(self.state, "data", self.state) if getattr(self, "state", None) else None
        payload = build_request_payload(self.question, self.session_id, state)
        return Data(data=payload)
