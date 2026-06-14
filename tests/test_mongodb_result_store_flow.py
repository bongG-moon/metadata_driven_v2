from __future__ import annotations

import importlib.util
import sys
import types
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_component(path: str):
    component_path = ROOT / path
    spec = importlib.util.spec_from_file_location(component_path.stem, component_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FakeCollection:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}

    def replace_one(self, query: dict[str, Any], doc: dict[str, Any], upsert: bool = False) -> None:
        self.docs[str(query["ref_id"])] = doc

    def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        return self.docs.get(str(query["ref_id"]))


class FakeDatabase:
    def __init__(self, collection: FakeCollection) -> None:
        self.collection = collection

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collection


class FakeClient:
    def __init__(self, collection: FakeCollection) -> None:
        self.collection = collection
        self.closed = False

    def __getitem__(self, name: str) -> FakeDatabase:
        return FakeDatabase(self.collection)

    def close(self) -> None:
        self.closed = True


def install_fake_pymongo(monkeypatch: Any, collection: FakeCollection) -> None:
    client = FakeClient(collection)

    def mongo_client(*args: Any, **kwargs: Any) -> FakeClient:
        return client

    monkeypatch.setitem(sys.modules, "pymongo", types.SimpleNamespace(MongoClient=mongo_client))


def test_mongodb_store_compacts_runtime_sources_and_loader_keeps_preview_by_default(monkeypatch: Any) -> None:
    store = load_component("langflow_components/main_flow/08_mongodb_data_store.py")
    loader = load_component("langflow_components/main_flow/01_mongodb_data_loader.py")
    collection = FakeCollection()
    install_fake_pymongo(monkeypatch, collection)
    rows = [{"PRODUCT": "A", "WIP": 10}, {"PRODUCT": "B", "WIP": 20}]
    payload = {
        "request": {"session_id": "session-1"},
        "runtime_sources": {"wip_total": rows},
        "source_results": [
            {
                "source_alias": "wip_total",
                "dataset_key": "wip_today",
                "source_type": "oracle",
                "row_count": 2,
                "columns": ["PRODUCT", "WIP"],
                "preview_rows": rows[:1],
                "data_ref": "source://oracle/wip_today/wip_total",
            }
        ],
    }

    stored = store.store_payload_in_mongodb(
        payload,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v2",
        result_collection_name="agent_v2_result_store",
        preview_row_limit="1",
        min_rows="1",
    )

    assert stored["mongo_data_store"]["stored"] is True
    assert stored["runtime_sources"]["wip_total"] == rows[:1]
    data_ref = stored["runtime_source_refs"]["wip_total"]
    assert data_ref["store"] == "mongodb"
    assert data_ref["collection_name"] == "agent_v2_result_store"
    assert stored["source_results"][0]["data_ref"]["ref_id"] == data_ref["ref_id"]
    assert collection.docs[data_ref["ref_id"]]["rows"] == rows

    hydrated = loader.load_payload_from_mongodb(
        stored,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v2",
        result_collection_name="agent_v2_result_store",
    )

    assert hydrated["runtime_sources"]["wip_total"] == rows[:1]
    assert hydrated["runtime_sources_are_preview"] is True
    assert hydrated["mongo_data_load"]["hydrate_mode"] == "preview"
    assert hydrated["mongo_data_load"]["loaded"] is False

    full = loader.load_payload_from_mongodb(
        stored,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v2",
        result_collection_name="agent_v2_result_store",
        hydrate_mode="full",
    )

    assert full["runtime_sources"]["wip_total"] == rows
    assert full["runtime_sources_are_preview"] is False
    assert full["mongo_data_load"]["loaded"] is True


def test_mongodb_store_compacts_final_data_and_loader_hydrates_preview_then_full(monkeypatch: Any) -> None:
    store = load_component("langflow_components/main_flow/08_mongodb_data_store.py")
    loader = load_component("langflow_components/main_flow/01_mongodb_data_loader.py")
    collection = FakeCollection()
    install_fake_pymongo(monkeypatch, collection)
    rows = [{"MODE": "LPDDR5", "WIP": 10}, {"MODE": "HBM", "WIP": 20}]
    payload = {
        "request": {"session_id": "session-1"},
        "data": {"columns": ["MODE", "WIP"], "rows": rows, "row_count": 2},
        "state": {"current_data": {"columns": ["MODE", "WIP"], "rows": rows, "row_count": 2}},
    }

    stored = store.store_payload_in_mongodb(
        payload,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v2",
        result_collection_name="agent_v2_result_store",
        preview_row_limit="1",
        min_rows="1",
    )

    assert stored["data"]["rows"] == rows[:1]
    assert stored["data"]["data_ref"]["store"] == "mongodb"
    assert stored["state"]["current_data"]["rows"] == rows[:1]
    assert stored["state"]["current_data"]["data_ref"]["store"] == "mongodb"

    hydrated = loader.load_payload_from_mongodb(
        stored,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v2",
        result_collection_name="agent_v2_result_store",
    )

    assert hydrated["data"]["rows"] == rows[:1]
    assert hydrated["data"]["data_ref_loaded"] is False
    assert hydrated["data"]["data_ref_load_mode"] == "preview"
    assert hydrated["state"]["current_data"]["rows"] == rows[:1]
    assert hydrated["state"]["current_data"]["data_ref_loaded"] is False

    full = loader.load_payload_from_mongodb(
        stored,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v2",
        result_collection_name="agent_v2_result_store",
        hydrate_mode="full",
    )

    assert full["data"]["rows"] == rows
    assert full["state"]["current_data"]["rows"] == rows
    assert full["state"]["current_data"]["data_ref_loaded"] is True

    auto_payload = deepcopy(stored)
    auto_payload["intent_plan"] = {"requires_full_state_hydrate": True}
    auto = loader.load_payload_from_mongodb(
        auto_payload,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v2",
        result_collection_name="agent_v2_result_store",
        hydrate_mode="auto",
    )

    assert auto["mongo_data_load"]["requested_hydrate_mode"] == "auto"
    assert auto["mongo_data_load"]["hydrate_mode"] == "full"
    assert auto["state"]["current_data"]["rows"] == rows


def test_mongodb_store_after_pandas_compacts_source_and_analysis_rows(monkeypatch: Any) -> None:
    store = load_component("langflow_components/main_flow/08_mongodb_data_store.py")
    collection = FakeCollection()
    install_fake_pymongo(monkeypatch, collection)
    source_rows = [{"MODE": "LPDDR5", "WIP": 10}, {"MODE": "HBM", "WIP": 20}]
    result_rows = [{"MODE": "LPDDR5", "WIP": 10}, {"MODE": "HBM", "WIP": 20}]
    payload = {
        "request": {"session_id": "session-1"},
        "runtime_sources": {"wip_data": source_rows},
        "source_results": [
            {
                "source_alias": "wip_data",
                "dataset_key": "wip_today",
                "source_type": "oracle",
                "row_count": 2,
                "columns": ["MODE", "WIP"],
            }
        ],
        "analysis": {
            "status": "ok",
            "columns": ["MODE", "WIP"],
            "rows": result_rows,
            "row_count": 2,
            "product_key_columns": ["MODE"],
            "product_key_values": [{"MODE": "LPDDR5"}, {"MODE": "HBM"}],
            "product_key_count": 2,
            "errors": [],
        },
    }

    stored = store.store_payload_in_mongodb(
        payload,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v2",
        result_collection_name="agent_v2_result_store",
        preview_row_limit="1",
        min_rows="1",
    )

    assert stored["mongo_data_store"]["stored"] is True
    assert stored["runtime_sources"]["wip_data"] == source_rows[:1]
    assert stored["analysis"]["rows"] == result_rows[:1]
    assert stored["analysis"]["data_ref"]["store"] == "mongodb"
    assert stored["source_results"][0]["data_ref"]["store"] == "mongodb"
    assert len(stored["data_refs"]) == 2
    assert collection.docs[stored["runtime_source_refs"]["wip_data"]["ref_id"]]["rows"] == source_rows
    assert collection.docs[stored["analysis"]["data_ref"]["ref_id"]]["rows"] == result_rows


def test_answer_response_state_keeps_product_key_summary_without_full_hydrate() -> None:
    answer_builder = load_component("langflow_components/main_flow/10_answer_response_builder.py")
    payload = {
        "request": {"session_id": "session-1", "question": "previous products"},
        "intent_plan": {"intent_type": "multi_step_analysis", "analysis_kind": "rank_wip_then_join_production", "product_grain": ["MODE"]},
        "analysis": {
            "columns": ["MODE", "WIP"],
            "rows": [{"MODE": "LPDDR5", "WIP": 10}],
            "row_count": 2,
            "data_ref": {"store": "mongodb", "ref_id": "result-ref", "collection_name": "agent_v2_result_store"},
            "data_is_reference": True,
            "data_is_preview": True,
            "product_key_columns": ["MODE"],
            "product_key_values": [{"MODE": "LPDDR5"}, {"MODE": "HBM"}],
            "product_key_count": 2,
        },
        "source_results": [],
        "state": {},
    }

    result = answer_builder.build_answer_response_payload(payload, '{"answer_message":"ok"}')

    assert result["state"]["current_data"]["product_key_columns"] == ["MODE"]
    assert result["state"]["current_data"]["product_key_values"] == [{"MODE": "LPDDR5"}, {"MODE": "HBM"}]
    assert result["state"]["current_data"]["product_key_count"] == 2
    assert result["data"]["data_ref"]["ref_id"] == "result-ref"
    assert result["state"]["current_data"]["data_ref"]["ref_id"] == "result-ref"
