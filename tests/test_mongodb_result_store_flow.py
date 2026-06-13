from __future__ import annotations

import importlib.util
import sys
import types
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


def test_mongodb_store_compacts_runtime_sources_and_loader_hydrates(monkeypatch: Any) -> None:
    store = load_component("langflow_components/main_flow/05_mongodb_data_store.py")
    loader = load_component("langflow_components/main_flow/06_mongodb_data_loader.py")
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

    assert hydrated["runtime_sources"]["wip_total"] == rows
    assert hydrated["runtime_sources_are_preview"] is False
    assert hydrated["mongo_data_load"]["loaded"] is True


def test_mongodb_store_compacts_final_data_and_loader_hydrates_current_data(monkeypatch: Any) -> None:
    store = load_component("langflow_components/main_flow/05_mongodb_data_store.py")
    loader = load_component("langflow_components/main_flow/06_mongodb_data_loader.py")
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

    assert hydrated["data"]["rows"] == rows
    assert hydrated["state"]["current_data"]["rows"] == rows
    assert hydrated["state"]["current_data"]["data_ref_loaded"] is True
