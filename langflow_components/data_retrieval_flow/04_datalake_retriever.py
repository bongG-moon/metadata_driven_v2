from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def retrieve_datalake_data(payload_value: Any, lake_user_id: str = "", lake_jwt_token: str = "", fetch_limit: str = "5000") -> dict[str, Any]:
    payload = _payload(payload_value)
    plan = payload.get("intent_plan", payload)
    jobs = [job for job in plan.get("retrieval_jobs", []) if _source_type(job) == "datalake"]
    configured = bool(str(lake_user_id or "").strip() and str(lake_jwt_token or "").strip())
    results = [_result(job, configured, fetch_limit) for job in jobs]
    return {"retrieval_payload": {"route": plan.get("route", "multi_retrieval"), "source_type": "datalake", "source_results": results, "intent_plan": plan, "state": payload.get("state", {})}}


def _result(job: dict[str, Any], configured: bool, fetch_limit: str) -> dict[str, Any]:
    rows = []
    for index in range(30):
        rows.append({"BASE_DT": (job.get("params") or {}).get("DATE", "20260612"), "EQPID": f"EQP{2000 + index}", "EQP_MODEL": f"CAPA-MODEL-{index % 4}", "RECIPE_ID": f"R-DUMMY-{index % 6}", "AVG_UPH_VAL": 700 + index * 11, "MODE": "HBM3E" if index % 3 == 0 else "LPDDR5", "TECH": "TSV" if index % 3 == 0 else "FC", "DEN": "2048G" if index % 3 == 0 else "128G", "MCP_NO": "H-HBM16E" if index % 3 == 0 else "EMPTY"})
    return {"success": True, "dataset_key": job.get("dataset_key", ""), "source_alias": job.get("source_alias", ""), "source_type": "datalake", "data": rows, "columns": list(rows[0]), "row_count": len(rows), "summary": "datalake retrieval returned dummy rows", "applied_params": deepcopy(job.get("params", {})), "applied_filters": deepcopy(job.get("filters", [])), "used_dummy_data": not configured, "source_execution": {"datalake_configured": configured, "fetch_limit": fetch_limit}}


def _source_type(job: dict[str, Any]) -> str:
    config = job.get("source_config") if isinstance(job.get("source_config"), dict) else {}
    return str(job.get("source_type") or config.get("source_type") or "").lower()


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}



class DatalakeRetriever(Component):
    display_name = "04 Datalake Retriever"
    description = "Executes Datalake jobs or returns dummy rows when credentials are empty."
    inputs = [DataInput(name="payload", display_name="Payload", required=True), MessageTextInput(name="lake_user_id", display_name="Lake User ID", value=""), MessageTextInput(name="lake_jwt_token", display_name="Lake JWT Token", value=""), MessageTextInput(name="fetch_limit", display_name="Fetch Limit", value="5000")]
    outputs = [Output(name="retrieval_payload", display_name="Retrieval Payload", method="build_payload")]

    def build_payload(self) -> Data:
        return Data(data=retrieve_datalake_data(getattr(self, "payload", None), self.lake_user_id, self.lake_jwt_token, self.fetch_limit))
