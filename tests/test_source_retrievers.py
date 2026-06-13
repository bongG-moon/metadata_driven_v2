from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from reference_runtime.metadata import load_metadata
from reference_runtime.source_retrievers import retrieve_rows_for_job


ROOT = Path(__file__).resolve().parents[1]


def test_table_catalog_uses_real_source_type_boundaries():
    catalog = json.loads((ROOT / "metadata" / "table_catalog.json").read_text(encoding="utf-8"))["datasets"]
    source_types = {item["source_type"] for item in catalog.values()}

    assert "sample_json" not in source_types
    assert {"oracle", "h_api", "datalake", "goodocs"}.issubset(source_types)


def test_reference_retriever_uses_source_type_with_dummy_fallback():
    metadata = load_metadata(ROOT)
    catalog = metadata["table_catalog"]["datasets"]
    expected = {
        "production_today": ("oracle", 100),
        "wip_today": ("oracle", 100),
        "lot_status": ("oracle", 100),
        "hold_history": ("h_api", 2),
        "target": ("goodocs", 10),
        "capacity": ("datalake", 20),
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
    module = _load_component("01_dummy_data_retriever.py")
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
                {"dataset_key": "production_today", "source_alias": "production_today", "source_type": "oracle", "params": {"DATE": "20260612"}},
                {"dataset_key": "hold_history", "source_alias": "hold_history", "source_type": "h_api", "params": {"LOT_ID": "T1234567GEN1"}},
                {"dataset_key": "capacity", "source_alias": "capacity", "source_type": "datalake", "params": {"DATE": "20260612"}},
                {"dataset_key": "target", "source_alias": "target", "source_type": "goodocs", "params": {"DATE": "2026-06-12"}},
            ],
        },
        "state": {},
    }

    oracle = _load_component("02_oracle_query_retriever.py").retrieve_oracle_data(plan)
    h_api = _load_component("03_h_api_retriever.py").retrieve_h_api_data(plan)
    datalake = _load_component("04_datalake_retriever.py").retrieve_datalake_data(plan)
    goodocs = _load_component("05_goodocs_retriever.py").retrieve_goodocs_data(plan)
    merged = _load_component("06_source_retrieval_merger.py").merge_source_retrieval_payloads(oracle, h_api, datalake, goodocs)

    source_types = [item["source_type"] for item in merged["retrieval_payload"]["source_results"]]
    assert source_types == ["oracle", "h_api", "datalake", "goodocs"]


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

    adapter = _load_main_component("04_retrieval_payload_adapter.py")
    payload = adapter.adapt_retrieval_payload(main_payload, retrieval_payload)

    assert payload["runtime_sources"]["hold_history"][0]["LOT_ID"] == "T1234567GEN1"
    assert "data" not in payload["source_results"][0]
    assert payload["source_results"][0]["preview_rows"][0]["HOLD_CD"] == "QA_HOLD"


def _load_component(filename: str):
    path = ROOT / "langflow_components" / "data_retrieval_flow" / filename
    spec = importlib.util.spec_from_file_location("test_" + path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_main_component(filename: str):
    path = ROOT / "langflow_components" / "main_flow" / filename
    spec = importlib.util.spec_from_file_location("test_" + path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
