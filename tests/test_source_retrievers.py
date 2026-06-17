from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from pathlib import Path

from reference_runtime.metadata import load_metadata
from reference_runtime.source_retrievers import retrieve_rows_for_job


ROOT = Path(__file__).resolve().parents[1]


def test_table_catalog_uses_real_source_type_boundaries():
    catalog = json.loads((ROOT / "metadata" / "table_catalog.json").read_text(encoding="utf-8"))["datasets"]
    source_types = {item["source_type"] for item in catalog.values()}

    assert "sample_json" not in source_types
    assert {"oracle", "goodocs"}.issubset(source_types)


def test_reference_retriever_uses_source_type_with_dummy_fallback():
    metadata = load_metadata(ROOT)
    catalog = metadata["table_catalog"]["datasets"]
    expected = {
        "production_today": ("oracle", 100),
        "wip_today": ("oracle", 100),
        "lot_status": ("oracle", 100),
        "hold_history": ("oracle", 2),
        "target": ("goodocs", 10),
        "capacity": ("oracle", 20),
    }

    for dataset_key, (source_type, minimum_rows) in expected.items():
        result = retrieve_rows_for_job(
            {
                "job_id": f"test_{dataset_key}",
                "dataset_key": dataset_key,
                "source_alias": dataset_key,
                "params": {"DATE": "20260612", "LOT_ID": "T1234567GEN1"},
            },
            catalog[dataset_key],
        )

        assert result["source_type"] == source_type
        assert result["used_dummy_data"] is True
        assert len(result["rows"]) >= minimum_rows
        assert result["source_execution"]["fallback_reason"]


def test_langflow_dummy_retriever_covers_all_current_datasets():
    module = _load_component("09_dummy_data_retriever.py")
    dataset_keys = [
        "production_today",
        "production",
        "wip_today",
        "wip",
        "target",
        "lot_status",
        "hold_history",
        "equipment_status",
        "capacity",
    ]
    payload = module.retrieve_dummy_data(
        {
            "intent_plan": {
                "route": "multi_retrieval",
                "retrieval_jobs": [
                    {"dataset_key": key, "source_alias": key, "params": {"DATE": "20260612", "LOT_ID": "T1234567GEN1"}}
                    for key in dataset_keys
                ],
            },
            "state": {},
        }
    )

    results = payload["retrieval_payload"]["source_results"]
    assert [item["dataset_key"] for item in results] == dataset_keys
    assert min(item["row_count"] for item in results if item["dataset_key"] != "hold_history") >= 8
    assert next(item for item in results if item["dataset_key"] == "lot_status")["row_count"] > 100


def test_langflow_source_retrievers_and_merger_preserve_source_types():
    plan = {
        "intent_plan": {
            "route": "multi_retrieval",
            "retrieval_jobs": [
                {
                    "dataset_key": "production_today",
                    "source_alias": "production_today",
                    "source_type": "oracle",
                    "source_config": {"source_type": "oracle", "db_key": "PNT_RPT", "query_template": "SELECT * FROM T WHERE WORK_DT = {DATE}"},
                    "params": {"DATE": "20260612"},
                },
                {
                    "dataset_key": "hold_history",
                    "source_alias": "hold_history",
                    "source_type": "h_api",
                    "source_config": {"source_type": "h_api", "api_url": "https://h-api.example.invalid", "response_path": "data.rows"},
                    "required_params": ["LOT_ID"],
                    "params": {"LOT_ID": "T1234567GEN1"},
                },
                {
                    "dataset_key": "capacity",
                    "source_alias": "capacity",
                    "source_type": "datalake",
                    "source_config": {"source_type": "datalake", "query_template": "SELECT * FROM T WHERE BASE_DT = {DATE}"},
                    "params": {"DATE": "20260612"},
                },
                {
                    "dataset_key": "target",
                    "source_alias": "target",
                    "source_type": "goodocs",
                    "source_config": {"source_type": "goodocs", "doc_id": "DOC", "sheet_name": "daily_target"},
                    "params": {"DATE": "2026-06-12"},
                    "filters": [{"field": "DATE", "op": "eq", "value": "2026-06-12"}],
                },
            ],
        },
        "state": {},
    }

    oracle = _load_component("10_oracle_query_retriever.py").retrieve_oracle_data(plan)
    h_api = _load_component("11_h_api_retriever.py").retrieve_h_api_data(plan)
    datalake = _load_component("12_datalake_retriever.py").retrieve_datalake_data(plan)
    goodocs = _load_component("13_goodocs_retriever.py").retrieve_goodocs_data(plan)
    merged = _load_component("14_source_retrieval_merger.py").merge_source_retrieval_payloads(oracle, h_api, datalake, goodocs)

    source_types = [item["source_type"] for item in merged["retrieval_payload"]["source_results"]]
    assert source_types == ["oracle", "h_api", "datalake", "goodocs"]


def test_langflow_oracle_retriever_executes_sql_when_configured():
    module = _load_component("10_oracle_query_retriever.py")

    class FakeCursor:
        description = [("WORK_DT",), ("PRODUCTION",)]

        def __init__(self) -> None:
            self.executed_sql = ""

        def execute(self, sql: str) -> None:
            self.executed_sql = sql

        def fetchmany(self, _limit: int):
            return [("20260612", 1234)]

        def close(self) -> None:
            pass

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_obj = FakeCursor()

        def cursor(self):
            return self.cursor_obj

        def close(self) -> None:
            pass

    class FakeOracleModule:
        def __init__(self) -> None:
            self.connection = FakeConnection()
            self.connect_kwargs = {}

        def connect(self, **kwargs):
            self.connect_kwargs = kwargs
            return self.connection

    fake_oracle = FakeOracleModule()
    module.OracleQueryRetriever.oracledb = fake_oracle
    plan = _source_plan(
        {
            "dataset_key": "production_today",
            "source_alias": "prod",
            "source_type": "oracle",
            "source_config": {"source_type": "oracle", "db_key": "PNT_RPT", "query_template": "SELECT WORK_DT, PRODUCTION FROM T WHERE WORK_DT = {DATE}"},
            "required_params": ["DATE"],
            "params": {"DATE": "20260612"},
        }
    )

    result = module.retrieve_oracle_data(plan, json.dumps({"PNT_RPT": {"user": "u", "password": "p", "dsn": "dsn"}}))
    source_result = result["retrieval_payload"]["source_results"][0]

    assert source_result["success"] is True
    assert source_result["used_dummy_data"] is False
    assert source_result["data"] == [{"WORK_DT": "20260612", "PRODUCTION": 1234}]
    assert source_result["executed_query"] == "SELECT WORK_DT, PRODUCTION FROM T WHERE WORK_DT = '20260612'"
    assert fake_oracle.connect_kwargs == {"user": "u", "password": "p", "dsn": "dsn"}


def test_langflow_h_api_retriever_posts_bind_params_when_token_is_present(monkeypatch):
    module = _load_component("11_h_api_retriever.py")
    captured = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self):
            return {"data": {"rows": [{"LOT_ID": "T1234567GEN1", "HOLD_CD": "QA_HOLD"}]}}

    def fake_post(url, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(post=fake_post))
    plan = _source_plan(
        {
            "dataset_key": "hold_history",
            "source_alias": "hold_history",
            "source_type": "h_api",
            "source_config": {"source_type": "h_api", "api_url": "https://h-api.example.invalid/hold", "response_path": "data.rows"},
            "required_params": ["LOT_ID"],
            "params": {"LOT_ID": "T1234567GEN1"},
        }
    )

    result = module.retrieve_h_api_data(plan, api_token="token")
    source_result = result["retrieval_payload"]["source_results"][0]

    assert source_result["success"] is True
    assert source_result["used_dummy_data"] is False
    assert source_result["data"][0]["HOLD_CD"] == "QA_HOLD"
    assert captured["json"] == {"bindParams": ["T1234567GEN1"]}


def test_langflow_datalake_retriever_uses_lakehouse_execution(monkeypatch):
    module = _load_component("12_datalake_retriever.py")
    calls = {}

    class FakeLakeHouse:
        def __init__(self, real_user_id: str) -> None:
            calls["real_user_id"] = real_user_id

        def ensure_running(self, cluster_type: str) -> None:
            calls["cluster_type"] = cluster_type

        def auto_run_sync_paragraph(self, code: str) -> None:
            calls["code"] = code

        def get_rst(self):
            return [{"BASE_DT": "20260612", "AVG_UPH_VAL": 777}]

    module.DatalakeRetriever.lakes = types.SimpleNamespace(LakeHouse=FakeLakeHouse)
    plan = _source_plan(
        {
            "dataset_key": "capacity",
            "source_alias": "capacity",
            "source_type": "datalake",
            "source_config": {"source_type": "datalake", "query_template": "SELECT BASE_DT, AVG_UPH_VAL FROM T WHERE BASE_DT = {DATE}"},
            "params": {"DATE": "20260612"},
        }
    )

    result = module.retrieve_datalake_data(plan, "lake-user", "lake-token", "access", "secret")
    source_result = result["retrieval_payload"]["source_results"][0]

    assert source_result["success"] is True
    assert source_result["used_dummy_data"] is False
    assert source_result["data"] == [{"BASE_DT": "20260612", "AVG_UPH_VAL": 777}]
    assert calls["code"] == "SELECT BASE_DT, AVG_UPH_VAL FROM T WHERE BASE_DT = '20260612'"
    assert os.environ["LAKEHOUSE_USER_ID"] == "lake-user"
    assert os.environ["LAKEHOUSE_S3_ACCESS_KEY"] == "access"


def test_langflow_goodocs_retriever_reads_document_and_applies_filters():
    module = _load_component("13_goodocs_retriever.py")
    captured = {}

    class FakeGoodocs:
        def __init__(self, auth: dict):
            captured["auth"] = auth

        def read_all(self):
            return [
                {"DATE": "2026-06-12", "MODE": "LPDDR5", "OUT_PLAN": 100, "ROW_ID": "drop"},
                {"DATE": "2026-06-13", "MODE": "LPDDR5", "OUT_PLAN": 200},
            ]

    module.GoodocsRetriever.goodocs_class = FakeGoodocs
    plan = _source_plan(
        {
            "dataset_key": "target",
            "source_alias": "target",
            "source_type": "goodocs",
            "source_config": {"source_type": "goodocs", "doc_id": "DOC", "sheet_name": "daily_target"},
            "params": {"DATE": "2026-06-12"},
            "filters": [{"field": "DATE", "op": "eq", "value": "2026-06-12"}],
        }
    )

    result = module.retrieve_goodocs_data(plan, "user", "source", "key")
    source_result = result["retrieval_payload"]["source_results"][0]

    assert source_result["success"] is True
    assert source_result["used_dummy_data"] is False
    assert source_result["data"] == [{"DATE": "2026-06-12", "MODE": "LPDDR5", "OUT_PLAN": 100}]
    assert captured["auth"]["DOC_ID"] == "DOC"
    assert captured["auth"]["SHEET_NAME"] == "daily_target"


def test_retrieval_payload_adapter_builds_compact_main_payload():
    main_payload = {
        "request": {"session_id": "test", "question": "q"},
        "state": {},
        "intent_plan": {
            "analysis_kind": "detail_rows",
            "retrieval_jobs": [{"dataset_key": "hold_history", "source_alias": "hold_history", "source_type": "h_api"}],
            "step_plan": [{"source_alias": "hold_history", "columns": ["LOT_ID", "HOLD_CD"]}],
        },
    }
    retrieval_payload = {
        "retrieval_payload": {
            "source_results": [
                {
                    "success": True,
                    "dataset_key": "hold_history",
                    "source_alias": "hold_history",
                    "source_type": "h_api",
                    "data": [{"LOT_ID": "T1234567GEN1", "HOLD_CD": "QA_HOLD"}],
                }
            ]
        }
    }

    adapter = _load_main_component("15_retrieval_payload_adapter.py")
    payload = adapter.adapt_retrieval_payload(main_payload, retrieval_payload)

    assert payload["runtime_sources"]["hold_history"][0]["LOT_ID"] == "T1234567GEN1"
    assert "data" not in payload["source_results"][0]
    assert payload["source_results"][0]["preview_rows"][0]["HOLD_CD"] == "QA_HOLD"


def test_retrieval_payload_adapter_preserves_full_restored_sources_without_new_retrieval():
    restored_rows = [
        {"DEVICE": "D1", "PRODUCTION": 10},
        {"DEVICE": "D2", "PRODUCTION": 20},
        {"DEVICE": "D3", "PRODUCTION": 30},
    ]
    main_payload = {
        "request": {"session_id": "test", "question": "이때 상세 device별로 알려줘"},
        "intent_plan": {"intent_type": "followup_transform", "requires_full_previous_result_restore": True},
        "runtime_sources": {"production_data": restored_rows},
        "runtime_sources_are_preview": False,
        "state": {
            "followup_source_results": [
                {
                    "source_alias": "production_data",
                    "dataset_key": "production_today",
                    "source_type": "oracle",
                    "data_ref": {
                        "store": "mongodb",
                        "ref_id": "source-ref",
                        "collection_name": "agent_v2_result_store",
                    },
                    "row_count": 3,
                    "columns": ["DEVICE", "PRODUCTION"],
                }
            ]
        },
    }
    retrieval_payload = {"retrieval_payload": {"source_results": []}}

    for adapter_path in [
        "langflow_components/data_analysis_flow/13_retrieval_payload_adapter.py",
        "langflow_components/data_analysis_flow/13_retrieval_payload_adapter.py",
    ]:
        adapter = _load_flow_component(adapter_path)
        payload = adapter.adapt_retrieval_payload(main_payload, retrieval_payload)

        assert payload["runtime_sources"]["production_data"] == restored_rows
        assert payload["source_results"][0]["data_ref"]["ref_id"] == "source-ref"
        assert payload["source_results"][0]["reused_from_previous_source"] is True
        assert payload["reused_previous_runtime_sources"] is True
        assert "이전 조회 원본을 새 조회 없이 재사용했습니다." in payload["info"]


def test_retrieval_payload_adapter_does_not_reuse_preview_sources_without_full_restore():
    main_payload = {
        "request": {"session_id": "test", "question": "상세 device별로 알려줘"},
        "intent_plan": {"intent_type": "single_retrieval_analysis"},
        "runtime_sources": {"production_data": [{"DEVICE": "D1", "PRODUCTION": 10}]},
        "runtime_sources_are_preview": True,
        "state": {},
    }
    retrieval_payload = {"retrieval_payload": {"source_results": []}}

    for adapter_path in [
        "langflow_components/data_analysis_flow/13_retrieval_payload_adapter.py",
        "langflow_components/data_analysis_flow/13_retrieval_payload_adapter.py",
    ]:
        adapter = _load_flow_component(adapter_path)
        payload = adapter.adapt_retrieval_payload(main_payload, retrieval_payload)

        assert payload["runtime_sources"] == {}
        assert payload["source_results"] == []
        assert "reused_previous_runtime_sources" not in payload


def _source_plan(job: dict) -> dict:
    return {"intent_plan": {"route": "single_retrieval", "retrieval_jobs": [job]}, "state": {}}


def _load_component(filename: str):
    mapped_filename = {
        "09_dummy_data_retriever.py": "07_dummy_data_retriever.py",
        "10_oracle_query_retriever.py": "08_oracle_query_retriever.py",
        "11_h_api_retriever.py": "09_h_api_retriever.py",
        "12_datalake_retriever.py": "10_datalake_retriever.py",
        "13_goodocs_retriever.py": "11_goodocs_retriever.py",
        "14_source_retrieval_merger.py": "12_source_retrieval_merger.py",
    }.get(filename, filename)
    path = ROOT / "langflow_components" / "data_analysis_flow" / mapped_filename
    spec = importlib.util.spec_from_file_location("test_" + path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_main_component(filename: str):
    mapped_filename = {
        "15_retrieval_payload_adapter.py": "13_retrieval_payload_adapter.py",
    }.get(filename, filename)
    path = ROOT / "langflow_components" / "data_analysis_flow" / mapped_filename
    spec = importlib.util.spec_from_file_location("test_" + path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_flow_component(relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location("test_" + path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
