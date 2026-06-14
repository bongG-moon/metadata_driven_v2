from __future__ import annotations

import json
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from reference_runtime.agent import run_agent


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SESSION_STATE = {"chat_history": [], "context": {}, "current_data": {}}
DEFAULT_REQUEST_DATE = "20260612"
PREVIEW_ROW_LIMIT = 20


class MockApiClient:
    """Python-only stand-in for Langflow Run APIs while API URLs are unavailable."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root else PROJECT_ROOT
        self.sessions: dict[str, dict[str, Any]] = {}
        self.result_store: dict[str, list[dict[str, Any]]] = {}
        self.pending_authoring: dict[str, dict[str, Any]] = {}

    def run_query(self, question: str, session_id: str = "demo-session", state: dict[str, Any] | None = None) -> dict[str, Any]:
        text = str(question or "").strip()
        if not text:
            raise ValueError("question is empty")
        session = str(session_id or "demo-session")
        previous_state = deepcopy(state if state is not None else self.sessions.get(session, DEFAULT_SESSION_STATE))
        payload = run_agent(text, state=previous_state, session_id=session, root=str(self.root), request_date=DEFAULT_REQUEST_DATE)
        compacted = self._compact_query_payload(payload, session)
        self.sessions[session] = deepcopy(compacted.get("state") or DEFAULT_SESSION_STATE)
        return compacted

    def get_rows(self, data_ref: dict[str, Any] | str) -> list[dict[str, Any]]:
        ref_id = data_ref if isinstance(data_ref, str) else (data_ref or {}).get("ref_id")
        return deepcopy(self.result_store.get(str(ref_id or ""), []))

    def list_metadata(self, metadata_type: str) -> list[dict[str, Any]]:
        kind = _normalize_metadata_type(metadata_type)
        if kind == "domain":
            domain = _load_json(self.root / "metadata" / "domain_items.json")
            rows: list[dict[str, Any]] = []
            for section, values in domain.items():
                if isinstance(values, dict):
                    for key, payload in values.items():
                        rows.append(
                            {
                                "type": "domain",
                                "section": section,
                                "key": key,
                                "status": "active",
                                "display_name": _payload_display_name(payload, key),
                                "aliases": _payload_aliases(payload),
                                "payload": payload,
                            }
                        )
                elif isinstance(values, list):
                    rows.append(
                        {
                            "type": "domain",
                            "section": section,
                            "key": section,
                            "status": "active",
                            "display_name": section,
                            "aliases": [],
                            "payload": {"values": values},
                        }
                    )
            return rows
        if kind == "table_catalog":
            catalog = _load_json(self.root / "metadata" / "table_catalog.json").get("datasets", {})
            return [
                {
                    "type": "table_catalog",
                    "dataset_key": key,
                    "status": "active",
                    "display_name": value.get("display_name", key) if isinstance(value, dict) else key,
                    "dataset_family": value.get("dataset_family", "") if isinstance(value, dict) else "",
                    "source_type": value.get("source_type", "") if isinstance(value, dict) else "",
                    "payload": value,
                }
                for key, value in catalog.items()
            ]
        filters = _load_json(self.root / "metadata" / "main_flow_filters.json")
        return [
            {
                "type": "main_flow_filter",
                "filter_key": key,
                "status": "active",
                "display_name": value.get("description", key) if isinstance(value, dict) else key,
                "column_candidates": value.get("column_candidates", []) if isinstance(value, dict) else [],
                "semantic_role": _guess_semantic_role(key),
                "payload": value,
            }
            for key, value in filters.items()
        ]

    def run_authoring(
        self,
        metadata_type: str,
        raw_text: str,
        duplicate_action: str = "ask",
        session_id: str = "demo-session",
    ) -> dict[str, Any]:
        kind = _normalize_metadata_type(metadata_type)
        action = _normalize_duplicate_action(duplicate_action)
        text = str(raw_text or "").strip()
        items = _build_authoring_items(kind, text)
        missing = _missing_information(kind, text, items)
        existing_matches, conflict_warnings = self._find_existing_matches(kind, items)
        requires_choice = action == "ask" and bool(existing_matches) and not missing

        review = {
            "ready_to_save": bool(items) and not missing and not requires_choice and action != "skip",
            "supplement_requests": missing,
            "review_summary": _review_summary(kind, missing, requires_choice),
        }
        write_result = _write_result_for(action, review, items, existing_matches)
        duplicate_decision = {"action": action, "requires_user_choice": requires_choice}
        response = {
            "status": write_result["status"],
            "message": _authoring_message(kind, write_result, missing, existing_matches, conflict_warnings),
            "metadata_type": kind,
            "items": items,
            "existing_matches": existing_matches,
            "conflict_warnings": conflict_warnings,
            "review": review,
            "write_result": write_result,
            "trace": {
                "raw_text": text,
                "refined_text": _refined_text(kind, text),
                "duplicate_decision": duplicate_decision,
                "api_mode": "python_mock",
            },
            "ui_status": _ui_status(write_result, missing, requires_choice, conflict_warnings),
        }
        if requires_choice:
            pending_id = f"pending-{uuid.uuid4().hex[:10]}"
            self.pending_authoring[pending_id] = {
                "metadata_type": kind,
                "raw_text": text,
                "last_response": deepcopy(response),
                "session_id": session_id,
            }
            response["pending_authoring_id"] = pending_id
        return response

    def validation_questions(self) -> list[dict[str, Any]]:
        return _load_json(self.root / "metadata" / "regression_questions.json")

    def validate_question(
        self,
        question: str,
        expected_datasets: list[str] | None = None,
        session_id: str = "validation-session",
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.run_query(question, session_id=session_id, state=state)
        actual = set((result.get("applied_scope") or {}).get("datasets") or [])
        expected = set(expected_datasets or [])
        passed = expected.issubset(actual) if expected else bool(result.get("answer_message"))
        return {
            "passed": passed,
            "expected_datasets": sorted(expected),
            "actual_datasets": sorted(actual),
            "result": result,
        }

    def _compact_query_payload(self, payload: dict[str, Any], session_id: str) -> dict[str, Any]:
        result = deepcopy(payload)
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        rows = list(data.get("rows") or [])
        if rows:
            data_ref = self._store_rows(rows, session_id, "data")
            data["rows"] = rows[:PREVIEW_ROW_LIMIT]
            data["data_ref"] = data_ref
            data["rows_are_preview"] = len(rows) > PREVIEW_ROW_LIMIT
            result["data"] = data
            current_data = ((result.get("state") or {}).get("current_data") or {}) if isinstance(result.get("state"), dict) else {}
            if isinstance(current_data, dict):
                current_data["rows"] = rows[:PREVIEW_ROW_LIMIT]
                current_data["data_ref"] = data_ref
                current_data["rows_are_preview"] = len(rows) > PREVIEW_ROW_LIMIT
                result.setdefault("state", {})["current_data"] = current_data
        result["api_mode"] = "python_mock"
        result["result_collection_name"] = "agent_v2_result_store"
        return result

    def _store_rows(self, rows: list[dict[str, Any]], session_id: str, path: str) -> dict[str, Any]:
        ref_id = f"mock-{uuid.uuid4().hex[:12]}"
        self.result_store[ref_id] = deepcopy(rows)
        return {
            "store": "python_mock",
            "collection_name": "agent_v2_result_store",
            "ref_id": ref_id,
            "session_id": session_id,
            "path": path,
            "row_count": len(rows),
        }

    def _find_existing_matches(self, metadata_type: str, items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        existing = self.list_metadata(metadata_type)
        matches: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        for item in items:
            new_key = _item_key(metadata_type, item)
            new_aliases = set(_payload_aliases(item.get("payload", {})))
            for old in existing:
                old_key = _item_key(metadata_type, old)
                old_aliases = set(old.get("aliases", []) or _payload_aliases(old.get("payload", {})))
                if new_key and old_key and str(new_key).lower() == str(old_key).lower():
                    matches.append(
                        {
                            "match_type": "same_key",
                            "similarity_level": "high",
                            "new_key": new_key,
                            "existing_key": old_key,
                            "reason": f"같은 key `{old_key}`가 이미 등록되어 있습니다.",
                            "recommended_action": "merge",
                            "existing": old,
                        }
                    )
                elif new_aliases and old_aliases and new_aliases.intersection(old_aliases):
                    warnings.append(
                        {
                            "warning_type": "alias_overlap",
                            "severity": "warning",
                            "new_key": new_key,
                            "existing_key": old_key,
                            "reason": "alias가 일부 겹칩니다. 같은 의미인지 확인하세요.",
                            "existing": old,
                        }
                    )
        return matches[:5], warnings[:5]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_metadata_type(value: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    if text in {"domain", "domains"}:
        return "domain"
    if text in {"table", "table_catalog", "catalog", "data_catalog"}:
        return "table_catalog"
    return "main_flow_filter"


def _normalize_duplicate_action(value: str) -> str:
    text = str(value or "ask").strip().lower()
    return text if text in {"ask", "merge", "replace", "skip", "create_new"} else "ask"


def _build_authoring_items(metadata_type: str, text: str) -> list[dict[str, Any]]:
    upper = text.upper()
    if metadata_type == "domain":
        if "COUNT_DISTINCT" in upper or "LOT" in upper:
            return [
                {
                    "section": "quantity_terms",
                    "key": "lot_count",
                    "status": "active",
                    "payload": {
                        "aliases": ["Lot 수량", "LOT 수량", "lot count"],
                        "dataset_key": "lot_status",
                        "quantity_column": "LOT_ID",
                        "aggregation": "nunique",
                        "output_column": "LOT_COUNT",
                    },
                }
            ]
        key = "WB" if "W/B" in upper or "WB" in upper else "DA"
        processes = [f"{'W/B' if key == 'WB' else 'D/A'}{index}" for index in range(1, 7)]
        return [
            {
                "section": "process_groups",
                "key": key,
                "status": "active",
                "payload": {
                    "display_name": "W/B" if key == "WB" else "D/A",
                    "aliases": [key, "W/B" if key == "WB" else "D/A"],
                    "processes": processes,
                },
            }
        ]
    if metadata_type == "table_catalog":
        dataset_key = "wip_today" if "WIP" in upper or "재공" in text else "production_today"
        quantity = "WIP" if dataset_key == "wip_today" else "PRODUCTION"
        query_template = _extract_query_template(text) or f"SELECT WORK_DT, OPER_NAME, {quantity} FROM MOCK_{dataset_key.upper()} WHERE WORK_DT = {{DATE}}"
        return [
            {
                "dataset_key": dataset_key,
                "status": "active",
                "payload": {
                    "display_name": "WIP Today" if dataset_key == "wip_today" else "Production Today",
                    "dataset_family": "wip" if dataset_key == "wip_today" else "production",
                    "date_scope": "current_day",
                    "source_type": "oracle",
                    "source_config": {"source_type": "oracle", "db_key": "PNT_RPT", "query_template": query_template},
                    "required_params": ["DATE"],
                    "required_param_mappings": {"DATE": ["WORK_DT"]},
                    "filter_mappings": {"DATE": ["WORK_DT"], "OPER_NAME": ["OPER_NAME"]},
                    "columns": ["WORK_DT", "OPER_NAME", quantity],
                    "primary_quantity_column": quantity,
                },
            }
        ]
    key = "DATE" if any(token in text for token in ("날짜", "기준일", "오늘", "금일", "DATE")) else "OPER_NAME"
    return [
        {
            "filter_key": key,
            "status": "active",
            "payload": {
                "display_name": "기준일" if key == "DATE" else "공정명",
                "aliases": ["오늘", "금일", "작업일"] if key == "DATE" else ["공정", "작업공정", "operation"],
                "column_candidates": ["WORK_DT", "DATE", "BASE_DT"] if key == "DATE" else ["OPER_NAME", "OPER_SHORT_DESC"],
                "semantic_role": "date" if key == "DATE" else "process_name",
                "value_type": "date" if key == "DATE" else "string",
                "value_shape": "scalar",
                "operator": "eq",
            },
        }
    ]


def _missing_information(metadata_type: str, text: str, items: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not text:
        return [{"field": "raw_text", "reason": "등록할 자연어 설명이 비어 있습니다.", "example_user_input": "DA는 D/A1부터 D/A6까지입니다."}]
    if not items:
        return [{"field": "items", "reason": "생성 가능한 metadata item을 찾지 못했습니다.", "example_user_input": "등록할 key와 의미를 설명해 주세요."}]
    if metadata_type == "table_catalog" and "SELECT" not in text.upper() and "DOC_ID" not in text.upper() and "API_URL" not in text.upper():
        return [
            {
                "field": "source_config.query_template",
                "reason": "운영 dataset 등록에는 source 조회 정보가 필요합니다.",
                "example_user_input": "wip_today는 SELECT ... WHERE WORK_DT = {DATE}로 조회합니다.",
            }
        ]
    return []


def _write_result_for(action: str, review: dict[str, Any], items: list[dict[str, Any]], matches: list[dict[str, Any]]) -> dict[str, Any]:
    base = {"status": "skipped", "saved_count": 0, "saved_items": [], "errors": [], "skipped_reason": ""}
    if action == "skip":
        base["skipped_reason"] = "사용자가 저장하지 않음을 선택했습니다."
        return base
    if matches and action == "ask":
        base["skipped_reason"] = "비슷한 기존 정보가 있어 merge/replace/skip/create_new 중 선택이 필요합니다."
        return base
    if not review.get("ready_to_save") and action not in {"merge", "replace", "create_new"}:
        base["skipped_reason"] = "검증 결과 저장할 수 없는 상태입니다."
        return base
    if review.get("supplement_requests"):
        base["skipped_reason"] = "필수 정보가 부족해 저장하지 않았습니다."
        return base
    return {
        "status": "ok",
        "saved_count": len(items),
        "saved_items": [_saved_item_summary(item) for item in items],
        "errors": [],
        "skipped_reason": "",
        "operation": action if action != "ask" else "insert",
    }


def _authoring_message(
    metadata_type: str,
    write_result: dict[str, Any],
    missing: list[dict[str, str]],
    matches: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> str:
    label = {"domain": "Domain", "table_catalog": "Table catalog", "main_flow_filter": "Main flow filter"}[metadata_type]
    if write_result.get("status") == "ok":
        return f"{label} metadata {write_result.get('saved_count', 0)}건을 mock 저장했습니다."
    if missing:
        return "아직 저장하지 않았습니다. 부족한 정보를 보완해 주세요."
    if matches:
        return "비슷한 기존 정보가 있어 처리 방식을 선택해야 합니다."
    if warnings:
        return "저장 전 확인할 경고가 있습니다."
    return write_result.get("skipped_reason") or "저장하지 않았습니다."


def _ui_status(write_result: dict[str, Any], missing: list[Any], requires_choice: bool, warnings: list[Any]) -> str:
    if write_result.get("status") == "ok" and warnings:
        return "warning"
    if write_result.get("status") == "ok":
        return "saved"
    if requires_choice:
        return "duplicate_choice_required"
    if missing:
        return "needs_more_input"
    if write_result.get("status") == "error":
        return "error"
    return "skipped"


def _refined_text(metadata_type: str, text: str) -> str:
    return f"[{metadata_type}] {text.strip()}" if text.strip() else ""


def _review_summary(metadata_type: str, missing: list[Any], requires_choice: bool) -> str:
    if missing:
        return "필수 정보가 부족합니다."
    if requires_choice:
        return "기존 metadata와 같은 key가 있어 사용자 선택이 필요합니다."
    return f"{metadata_type} item을 저장할 수 있는 mock 검토 상태입니다."


def _extract_query_template(text: str) -> str:
    marker = "SELECT "
    upper = text.upper()
    index = upper.find(marker)
    if index < 0:
        return ""
    return text[index:].strip()


def _item_key(metadata_type: str, item: dict[str, Any]) -> str:
    if metadata_type == "domain":
        return f"{item.get('section')}/{item.get('key')}"
    if metadata_type == "table_catalog":
        return str(item.get("dataset_key") or "")
    return str(item.get("filter_key") or "")


def _payload_display_name(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        return str(payload.get("display_name") or fallback)
    return str(fallback)


def _payload_aliases(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    aliases = payload.get("aliases")
    return [str(item) for item in aliases] if isinstance(aliases, list) else []


def _saved_item_summary(item: dict[str, Any]) -> dict[str, Any]:
    result = {key: item.get(key) for key in ("section", "key", "dataset_key", "filter_key") if item.get(key)}
    result["_id"] = ":".join(str(value) for value in result.values())
    return result


def _guess_semantic_role(key: str) -> str:
    if key == "DATE":
        return "date"
    if key == "OPER_NAME":
        return "process_name"
    if key.startswith("LOT"):
        return "lot"
    if key.startswith("EQP"):
        return "equipment"
    return "product_attribute"
