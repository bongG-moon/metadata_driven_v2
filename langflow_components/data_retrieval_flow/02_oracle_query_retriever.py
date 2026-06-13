from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def retrieve_oracle_data(payload_value: Any, oracle_config: str = "", fetch_limit: str = "5000") -> dict[str, Any]:
    return _retrieve_source(payload_value, "oracle", {"oracle_configured": bool(str(oracle_config or "").strip()), "fetch_limit": fetch_limit})


def _retrieve_source(payload_value: Any, source_type: str, extra: dict[str, Any]) -> dict[str, Any]:
    payload = _payload(payload_value)
    plan = payload.get("intent_plan", payload)
    jobs = [job for job in plan.get("retrieval_jobs", []) if _source_type(job) == source_type]
    results = [_source_result(job, source_type, extra) for job in jobs]
    return {"retrieval_payload": {"route": plan.get("route", "multi_retrieval"), "source_type": source_type, "source_results": results, "intent_plan": plan, "state": payload.get("state", {})}}


def _source_result(job: dict[str, Any], source_type: str, extra: dict[str, Any]) -> dict[str, Any]:
    rows = _dummy_rows(job, source_type)
    return {"success": True, "dataset_key": job.get("dataset_key", ""), "source_alias": job.get("source_alias", job.get("dataset_key", "")), "source_type": source_type, "data": rows, "columns": list(rows[0].keys()) if rows else [], "row_count": len(rows), "summary": f"{source_type} retrieval returned dummy rows", "applied_params": deepcopy(job.get("params", {})), "applied_filters": deepcopy(job.get("filters", [])), "used_dummy_data": not extra.get("oracle_configured"), "source_execution": extra}


def _dummy_rows(job: dict[str, Any], source_type: str) -> list[dict[str, Any]]:
    columns = job.get("required_columns") or ["WORK_DT", "OPER_NAME", "TECH", "DEN", "MODE", "PRODUCTION", "WIP"]
    rows = []
    for index in range(40):
        base = {"WORK_DT": (job.get("params") or {}).get("DATE", "20260612"), "OPER_NAME": ["D/A1", "D/A2", "W/B1", "B/G1"][index % 4], "TECH": "TSV" if index % 5 == 0 else "FC", "DEN": "2048G" if index % 5 == 0 else "128G", "MODE": "HBM3E" if index % 5 == 0 else "LPDDR5", "PRODUCTION": 10000 + index * 100, "WIP": 20000 + index * 150}
        rows.append({column: base.get(column) for column in columns if column in base})
    return rows


def _source_type(job: dict[str, Any]) -> str:
    config = job.get("source_config") if isinstance(job.get("source_config"), dict) else {}
    return str(job.get("source_type") or config.get("source_type") or "oracle").lower()


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}



class OracleQueryRetriever(Component):
    display_name = "02 Oracle Query Retriever"
    description = "Executes oracle jobs or returns dummy rows when config is empty."
    inputs = [DataInput(name="payload", display_name="Payload", required=True), MessageTextInput(name="oracle_config", display_name="Oracle Config", value=""), MessageTextInput(name="fetch_limit", display_name="Fetch Limit", value="5000")]
    outputs = [Output(name="retrieval_payload", display_name="Retrieval Payload", method="build_payload")]

    def build_payload(self) -> Data:
        return Data(data=retrieve_oracle_data(getattr(self, "payload", None), self.oracle_config, self.fetch_limit))
