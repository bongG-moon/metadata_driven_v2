from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def adapt_retrieval_payload(main_payload_value: Any, retrieval_payload_value: Any) -> dict[str, Any]:
    main_payload = _payload(main_payload_value)
    if main_payload.get("direct_response_ready"):
        return main_payload
    retrieval_wrapper = _payload(retrieval_payload_value)
    retrieval_payload = (
        retrieval_wrapper.get("retrieval_payload")
        if isinstance(retrieval_wrapper.get("retrieval_payload"), dict)
        else retrieval_wrapper
    )

    runtime_sources: dict[str, list[dict[str, Any]]] = {}
    compact_results: list[dict[str, Any]] = []
    errors: list[str] = []
    metadata = main_payload.get("metadata") if isinstance(main_payload.get("metadata"), dict) else {}

    for result in retrieval_payload.get("source_results", []):
        if not isinstance(result, dict):
            continue
        source_alias = str(result.get("source_alias") or result.get("dataset_key") or "")
        dataset_key = str(result.get("dataset_key") or "")
        source_type = str(result.get("source_type") or "dummy")
        rows = _standardize_rows_for_dataset(dataset_key, _rows_from_result(result), metadata)
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


def _standardize_rows_for_dataset(dataset_key: str, rows: list[dict[str, Any]], metadata: dict[str, Any]) -> list[dict[str, Any]]:
    if not rows:
        return rows
    catalog = (((metadata.get("table_catalog") or {}).get("datasets") or {}).get(dataset_key) or {}) if isinstance(metadata, dict) else {}
    if not isinstance(catalog, dict):
        catalog = {}
    aliases = _standard_aliases(catalog)
    if not aliases:
        return rows
    standardized = []
    for row in rows:
        clean_row = dict(row)
        for standard, candidates in aliases.items():
            if clean_row.get(standard) not in (None, ""):
                continue
            for candidate in candidates:
                if clean_row.get(candidate) not in (None, ""):
                    clean_row[standard] = clean_row[candidate]
                    break
        standardized.append(clean_row)
    return standardized


def _standard_aliases(catalog: dict[str, Any]) -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = {
        "INPUT_PLAN": ["INPUT계획"],
        "OUT_PLAN": ["OUT계획", "TARGET"],
        "PKG_TYPE1": ["PKG1", "PKG_TYP"],
        "PKG_TYPE2": ["PKG2", "PKG_TYP_2", "PKG_TYP2"],
        "MCP_NO": ["MCP NO", "MCPSALENO", "PROD_GRP_ID", "MCP_SALE_CD"],
        "MODE": ["Mode", "PROD_TYP"],
        "TECH": ["TECH_NM"],
        "DEN": ["DEN_TYP"],
        "LEAD": ["LEAD_CNT"],
        "EQP_MODEL": ["EQP_MODEL_CD"],
    }
    filter_mappings = catalog.get("filter_mappings") if isinstance(catalog.get("filter_mappings"), dict) else {}
    for standard, candidates in filter_mappings.items():
        if not isinstance(candidates, list):
            candidates = [candidates]
        aliases.setdefault(str(standard), [])
        aliases[str(standard)].extend(str(item) for item in candidates if str(item or "").strip())
    configured = catalog.get("standard_column_aliases") if isinstance(catalog.get("standard_column_aliases"), dict) else {}
    for standard, candidates in configured.items():
        if not isinstance(candidates, list):
            candidates = [candidates]
        aliases.setdefault(str(standard), [])
        aliases[str(standard)].extend(str(item) for item in candidates if str(item or "").strip())
    return {key: _unique([item for item in values if item != key]) for key, values in aliases.items()}


def _unique(values: list[Any]) -> list[str]:
    result = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}



class RetrievalPayloadAdapter(Component):
    display_name = "05 Retrieval Payload Adapter"
    description = "Converts merged source retrieval payload into main flow runtime_sources and compact source_results."
    inputs = [
        DataInput(name="main_payload", display_name="Main Payload", required=True),
        DataInput(name="retrieval_payload", display_name="Retrieval Payload", required=True),
    ]
    outputs = [Output(name="payload", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        return Data(data=adapt_retrieval_payload(self.main_payload, self.retrieval_payload))
