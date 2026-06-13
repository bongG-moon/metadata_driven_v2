from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


PRODUCTS = [
    {"TECH": "TSV", "DEN": "2048G", "MODE": "HBM3E", "PKG_TYPE1": "HBM", "PKG_TYPE2": "HBM", "LEAD": "LF", "MCP_NO": "H-HBM16E", "TSV_DIE_TYP": "16Hi"},
    {"TECH": "TSV", "DEN": "1536G", "MODE": "HBM3", "PKG_TYPE1": "HBM", "PKG_TYPE2": "HBM", "LEAD": "LF", "MCP_NO": "H-HBM12A", "TSV_DIE_TYP": "12Hi"},
    {"TECH": "TSV", "DEN": "1024G", "MODE": "HBM3", "PKG_TYPE1": "HBM", "PKG_TYPE2": "HBM", "LEAD": "LF", "MCP_NO": "H-HBM8A", "TSV_DIE_TYP": "8Hi"},
    {"TECH": "FC", "DEN": "128G", "MODE": "LPDDR5", "PKG_TYPE1": "UFBGA", "PKG_TYPE2": "MOBILE", "LEAD": "LF", "MCP_NO": "EMPTY", "TSV_DIE_TYP": ""},
    {"TECH": "FC", "DEN": "256G", "MODE": "LPDDR5", "PKG_TYPE1": "LFBGA", "PKG_TYPE2": "EDGE", "LEAD": "LF", "MCP_NO": "L-269E1D", "TSV_DIE_TYP": ""},
    {"TECH": "WB", "DEN": "512G", "MODE": "DDR5", "PKG_TYPE1": "FCBGA", "PKG_TYPE2": "AUTO", "LEAD": "LF", "MCP_NO": "L-111K1Q", "TSV_DIE_TYP": ""},
    {"TECH": "WB", "DEN": "1024G", "MODE": "DDR5", "PKG_TYPE1": "FCBGA", "PKG_TYPE2": "SERVER", "LEAD": "LF", "MCP_NO": "L-555S1E", "TSV_DIE_TYP": ""},
    {"TECH": "POP", "DEN": "128G", "MODE": "MCP", "PKG_TYPE1": "LFBGA", "PKG_TYPE2": "MCP", "LEAD": "LF", "MCP_NO": "L-269M2B", "TSV_DIE_TYP": ""},
]
PROCESSES = ["D/A1", "D/A2", "D/A3", "W/B1", "W/B2", "W/B3", "B/G1", "B/G2", "WSD1", "D/P1", "FCB1", "INPUT"]


def retrieve_dummy_data(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    plan = payload.get("intent_plan", payload)
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else payload.get("retrieval_jobs", [])
    source_results = [_source_result(job, "dummy") for job in jobs if isinstance(job, dict)]
    return {"retrieval_payload": {"route": plan.get("route", "multi_retrieval"), "source_type": "dummy", "source_results": source_results, "intent_plan": plan, "state": payload.get("state", {})}}


def _source_result(job: dict[str, Any], source_type: str) -> dict[str, Any]:
    rows = _dummy_rows(job, source_type)
    return {
        "success": True,
        "dataset_key": job.get("dataset_key", ""),
        "source_alias": job.get("source_alias", job.get("dataset_key", "")),
        "source_type": source_type,
        "data": rows,
        "columns": list(rows[0].keys()) if rows else [],
        "row_count": len(rows),
        "summary": f"{source_type} dummy rows: {len(rows)}",
        "applied_params": deepcopy(job.get("params", {})),
        "applied_filters": deepcopy(job.get("filters", [])),
        "used_dummy_data": True,
    }


def _dummy_rows(job: dict[str, Any], source_type: str) -> list[dict[str, Any]]:
    dataset_key = str(job.get("dataset_key") or "dataset")
    date_value = (job.get("params") or {}).get("DATE", "20260612")
    if dataset_key in {"production_today", "production"}:
        rows = _process_product_rows(date_value, "PRODUCTION")
    elif dataset_key in {"wip_today", "wip"}:
        rows = _process_product_rows(date_value, "WIP")
    elif dataset_key == "target":
        rows = _target_rows()
    elif dataset_key == "hold_history":
        rows = _hold_rows((job.get("params") or {}).get("LOT_ID", "T1234567GEN1"))
    elif dataset_key == "lot_status":
        rows = _lot_rows(date_value)
    elif dataset_key == "equipment_status":
        rows = _equipment_rows(date_value, source_type)
    elif dataset_key == "capacity":
        rows = _capacity_rows(date_value)
    else:
        rows = _process_product_rows(date_value, "PRODUCTION")
    columns = job.get("required_columns")
    if columns:
        return [{column: row.get(column) for column in columns if column in row} for row in rows]
    return rows


def _process_product_rows(date_value: str, quantity_column: str) -> list[dict[str, Any]]:
    rows = []
    for process_index, process in enumerate(PROCESSES, start=1):
        for product_index, product in enumerate(PRODUCTS, start=1):
            row = {"WORK_DT": date_value, "OPER_NAME": process, "OPER_SHORT_DESC": process, **product}
            row[quantity_column] = 1000 + process_index * 310 + product_index * 145
            rows.append(row)
    return rows


def _target_rows() -> list[dict[str, Any]]:
    rows = []
    for index, product in enumerate(PRODUCTS, start=1):
        rows.append({"DATE": "2026-06-12", **product, "INPUT_PLAN": 100000 + index * 8500, "OUT_PLAN": 82000 + index * 6200})
    return rows


def _hold_rows(lot_id: str) -> list[dict[str, Any]]:
    return [
        {"LOT_ID": lot_id, "HOLD_TM": "2026-06-12 09:10:00", "HOLD_CD": "QA_HOLD", "HOLD_DESC": "QA review hold", "HOLD_USER_ID": "qa_user", "EVENT_CD": "HOLD"},
        {"LOT_ID": lot_id, "HOLD_TM": "2026-06-12 11:30:00", "HOLD_CD": "RECIPE_CHECK", "HOLD_DESC": "Recipe approval check", "HOLD_USER_ID": "process_eng", "EVENT_CD": "RELEASE"},
    ]


def _lot_rows(date_value: str) -> list[dict[str, Any]]:
    rows = [{"WORK_DT": date_value, "LOT_ID": "T1234567GEN1", "OPER_SHORT_DESC": "D/A1", "LOT_STAT_CD": "RUNNING", "LOT_HOLD_STAT_CD": "HOLD", **PRODUCTS[0], "SUB_PROD_QTY": 1200, "WF_QTY": 25, "IN_TAT": 12.5, "CUM_TAT": 88.0}]
    index = 0
    for process in PROCESSES[:10]:
        for product in PRODUCTS:
            for slot in range(2):
                index += 1
                rows.append({"WORK_DT": date_value, "LOT_ID": f"LOT{date_value[-4:]}{index:05d}", "OPER_SHORT_DESC": process, "LOT_STAT_CD": "WAITING" if index % 2 else "RUNNING", "LOT_HOLD_STAT_CD": "HOLD" if index % 7 == 0 else "", **product, "SUB_PROD_QTY": 900 + index * 8, "WF_QTY": 12 + index % 16, "IN_TAT": 2.5 + index % 9, "CUM_TAT": 18.0 + index % 40})
    return rows


def _equipment_rows(date_value: str, source_type: str) -> list[dict[str, Any]]:
    rows = []
    for index, product in enumerate(PRODUCTS * 3, start=1):
        rows.append({"BASE_DT": date_value, "EQPID": f"EQP{1000 + index}", "EQP_ID": f"EQP{1000 + index}", "EQP_MODEL": f"{source_type.upper()}-MODEL-{index % 5}", "PRESS_CNT": 1 + index % 3, "LOT_ID": "T1234567GEN1" if index <= 2 else f"LOT{date_value[-4:]}{index:05d}", "RECIPE_ID": f"R-{product['MODE']}-{index % 4}", **product})
    return rows


def _capacity_rows(date_value: str) -> list[dict[str, Any]]:
    rows = []
    for index, product in enumerate(PRODUCTS * 2, start=1):
        rows.append({"BASE_DT": date_value, "EQPID": f"EQP{2000 + index}", "EQP_MODEL": f"CAPA-{product['PKG_TYPE1']}-{index % 3}", "RECIPE_ID": f"R-{product['MODE']}-{index % 4}", "AVG_UPH_VAL": 650 + index * 45, "PRESS_CNT": 1 + index % 2, **product})
    return rows


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}



class DummyDataRetriever(Component):
    display_name = "01 Dummy Data Retriever"
    description = "Returns rich deterministic dummy rows for local retrieval validation."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="retrieval_payload", display_name="Retrieval Payload", method="build_payload")]

    def build_payload(self) -> Data:
        return Data(data=retrieve_dummy_data(getattr(self, "payload", None)))
