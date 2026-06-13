from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def adapt_retrieval_payload(main_payload_value: Any, retrieval_payload_value: Any) -> dict[str, Any]:
    main_payload = _payload(main_payload_value)
    retrieval_wrapper = _payload(retrieval_payload_value)
    retrieval_payload = (
        retrieval_wrapper.get("retrieval_payload")
        if isinstance(retrieval_wrapper.get("retrieval_payload"), dict)
        else retrieval_wrapper
    )

    runtime_sources: dict[str, list[dict[str, Any]]] = {}
    compact_results: list[dict[str, Any]] = []
    errors: list[str] = []

    for result in retrieval_payload.get("source_results", []):
        if not isinstance(result, dict):
            continue
        source_alias = str(result.get("source_alias") or result.get("dataset_key") or "")
        dataset_key = str(result.get("dataset_key") or "")
        source_type = str(result.get("source_type") or "dummy")
        rows = _rows_from_result(result)
        runtime_sources[source_alias] = rows

        compact = deepcopy(result)
        compact.pop("data", None)
        compact.pop("rows", None)
        compact.setdefault("source_alias", source_alias)
        compact.setdefault("dataset_key", dataset_key)
        compact.setdefault("source_type", source_type)
        compact.setdefault("row_count", len(rows))
        compact.setdefault("columns", list(rows[0].keys()) if rows else [])
        compact.setdefault("preview_rows", deepcopy(rows[:5]))
        compact.setdefault("data_ref", f"source://{source_type}/{dataset_key}/{source_alias}")
        compact_results.append(compact)

        if result.get("success") is False:
            errors.append(str(result.get("error_message") or result.get("summary") or f"{dataset_key} retrieval failed"))

    next_payload = deepcopy(main_payload)
    next_payload["runtime_sources"] = runtime_sources
    next_payload["source_results"] = compact_results
    next_payload["status"] = "warning" if errors else next_payload.get("status", "ok")
    next_payload["errors"] = list(next_payload.get("errors", [])) + errors
    return next_payload


def _rows_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = result.get("data")
    if rows is None:
        rows = result.get("rows")
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}



class RetrievalPayloadAdapter(Component):
    display_name = "04 Retrieval Payload Adapter"
    description = "Converts merged source retrieval payload into main flow runtime_sources and compact source_results."
    inputs = [
        DataInput(name="main_payload", display_name="Main Payload", required=True),
        DataInput(name="retrieval_payload", display_name="Retrieval Payload", required=True),
    ]
    outputs = [Output(name="payload", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        return Data(data=adapt_retrieval_payload(self.main_payload, self.retrieval_payload))
