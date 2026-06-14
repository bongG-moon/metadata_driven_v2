from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


SOURCE_REQUIRED_FIELDS = {
    "oracle": ["db_key", "query_template"],
    "h_api": ["api_url"],
    "datalake": ["query_template"],
    "goodocs": ["doc_id", "sheet_name"],
}


def normalize_table_catalog_authoring_result(payload_value: Any, llm_response_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    parsed = _extract_json_object(_text(llm_response_value))
    errors = []
    items = []
    if not parsed:
        errors.append("저장 형식 변환 LLM 응답에서 JSON을 찾지 못했습니다.")
    raw_items = parsed.get("items") if isinstance(parsed.get("items"), list) else []
    for index, raw_item in enumerate(raw_items):
        item, item_errors = _normalize_item(raw_item, index)
        if item:
            items.append(item)
        errors.extend(item_errors)
    next_payload = dict(payload)
    next_payload["items"] = items
    next_payload["authoring"] = {
        "missing_information": _as_list(parsed.get("missing_information")),
        "warnings": _as_list(parsed.get("warnings")),
        "raw_item_count": len(raw_items),
    }
    next_payload["errors"] = list(next_payload.get("errors", [])) + errors
    next_payload["warnings"] = list(next_payload.get("warnings", [])) + [str(item) for item in _as_list(parsed.get("warnings"))]
    return next_payload


def _normalize_item(raw_item: Any, index: int) -> tuple[dict[str, Any] | None, list[str]]:
    errors = []
    if not isinstance(raw_item, dict):
        return None, [f"items[{index}]가 object가 아닙니다."]
    dataset_key = _clean(raw_item.get("dataset_key") or raw_item.get("key"))
    payload = deepcopy(raw_item.get("payload")) if isinstance(raw_item.get("payload"), dict) else {}
    if not dataset_key:
        errors.append(f"items[{index}] dataset_key가 없습니다.")
    source_type = _clean(payload.get("source_type") or (payload.get("source_config") or {}).get("source_type") or "dummy").lower()
    payload["source_type"] = source_type
    source_config = deepcopy(payload.get("source_config")) if isinstance(payload.get("source_config"), dict) else {}
    source_config.setdefault("source_type", source_type)
    payload["source_config"] = source_config
    for field in SOURCE_REQUIRED_FIELDS.get(source_type, []):
        if not _clean(source_config.get(field)):
            errors.append(f"{dataset_key} source_type={source_type}에는 source_config.{field}가 필요합니다.")
    if not _clean(payload.get("dataset_family")):
        errors.append(f"{dataset_key} dataset_family가 필요합니다.")
    if not _as_text_list(payload.get("columns")):
        errors.append(f"{dataset_key} columns 목록이 필요합니다.")
    if not isinstance(payload.get("filter_mappings"), dict):
        payload["filter_mappings"] = {}
    else:
        payload["filter_mappings"] = {
            _clean(key): _as_text_list(value)
            for key, value in payload["filter_mappings"].items()
            if _clean(key)
        }
    if not isinstance(payload.get("required_params"), list):
        payload["required_params"] = _as_text_list(payload.get("required_params"))
    if payload.get("default_detail_columns") is not None:
        payload["default_detail_columns"] = _as_text_list(payload.get("default_detail_columns"))
    if payload.get("columns") is not None:
        payload["columns"] = _as_text_list(payload.get("columns"))
    return {
        "dataset_key": dataset_key,
        "key": dataset_key,
        "status": _clean(raw_item.get("status") or "active"),
        "payload": payload,
        "confidence": _clean(raw_item.get("confidence") or "medium"),
    }, errors


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


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    result = []
    for item in value:
        text = _clean(item)
        if text and text not in result:
            result.append(text)
    return result


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


def _clean(value: Any) -> str:
    return str(value or "").strip()


class TableCatalogAuthoringResultNormalizer(Component):
    display_name = "04 Table Catalog Authoring Result Normalizer"
    description = "Normalizes the table catalog authoring LLM JSON into MongoDB-ready dataset items."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="llm_response", display_name="LLM Response", required=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        result = normalize_table_catalog_authoring_result(getattr(self, "payload", None), getattr(self, "llm_response", ""))
        self.status = {"items": len(result.get("items", [])), "errors": len(result.get("errors", []))}
        return Data(data=result)
