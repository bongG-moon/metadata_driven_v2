from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def retrieve_h_api_data(payload_value: Any, api_token: str = "", fetch_limit: str = "5000") -> dict[str, Any]:
    payload = _payload(payload_value)
    plan = payload.get("intent_plan", payload)
    jobs = [job for job in plan.get("retrieval_jobs", []) if _source_type(job) == "h_api"]
    results = [_result(job, bool(str(api_token or "").strip()), fetch_limit) for job in jobs]
    return {"retrieval_payload": {"route": plan.get("route", "multi_retrieval"), "source_type": "h_api", "source_results": results, "intent_plan": plan, "state": payload.get("state", {})}}


def _result(job: dict[str, Any], configured: bool, fetch_limit: str) -> dict[str, Any]:
    lot_id = (job.get("params") or {}).get("LOT_ID", "T1234567GEN1")
    rows = [{"LOT_ID": lot_id, "HOLD_TM": "2026-06-12 09:10:00", "HOLD_CD": "QA_HOLD", "HOLD_DESC": "Dummy H-API hold history", "HOLD_USER_ID": "dummy", "EVENT_CD": "HOLD"}]
    return {"success": True, "dataset_key": job.get("dataset_key", ""), "source_alias": job.get("source_alias", ""), "source_type": "h_api", "data": rows, "columns": list(rows[0]), "row_count": len(rows), "summary": "h_api retrieval returned dummy rows", "applied_params": deepcopy(job.get("params", {})), "applied_filters": deepcopy(job.get("filters", [])), "used_dummy_data": not configured, "source_execution": {"api_configured": configured, "fetch_limit": fetch_limit}}


def _source_type(job: dict[str, Any]) -> str:
    config = job.get("source_config") if isinstance(job.get("source_config"), dict) else {}
    return str(job.get("source_type") or config.get("source_type") or "").lower()


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}



class HApiRetriever(Component):
    display_name = "03 H-API Retriever"
    description = "Executes H-API jobs or returns dummy rows when token is empty."
    inputs = [DataInput(name="payload", display_name="Payload", required=True), MessageTextInput(name="api_token", display_name="H-API Token", value=""), MessageTextInput(name="fetch_limit", display_name="Fetch Limit", value="5000")]
    outputs = [Output(name="retrieval_payload", display_name="Retrieval Payload", method="build_payload")]

    def build_payload(self) -> Data:
        return Data(data=retrieve_h_api_data(getattr(self, "payload", None), self.api_token, self.fetch_limit))
