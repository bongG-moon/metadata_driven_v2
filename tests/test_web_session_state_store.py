from __future__ import annotations

import sys
import types
from typing import Any

from web_app import langflow_client
from web_app.langflow_client import LangflowApiClient, LangflowSettings


class FakeCollection:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}

    def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        if "_id" in query:
            return self.docs.get(str(query["_id"]))
        if "session_id" in query:
            for doc in self.docs.values():
                if doc.get("session_id") == query["session_id"]:
                    return doc
        return None

    def replace_one(self, query: dict[str, Any], doc: dict[str, Any], upsert: bool = False) -> None:
        self.docs[str(query["_id"])] = doc


class FakeDatabase:
    def __init__(self, collection: FakeCollection) -> None:
        self.collection = collection

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collection


class FakeClient:
    def __init__(self, collection: FakeCollection) -> None:
        self.collection = collection

    def __getitem__(self, name: str) -> FakeDatabase:
        return FakeDatabase(self.collection)

    def close(self) -> None:
        return None


def install_fake_pymongo(monkeypatch: Any, collection: FakeCollection) -> None:
    client = FakeClient(collection)

    def mongo_client(*args: Any, **kwargs: Any) -> FakeClient:
        return client

    monkeypatch.setitem(sys.modules, "pymongo", types.SimpleNamespace(MongoClient=mongo_client))


def test_langflow_client_loads_and_saves_mongodb_session_state(monkeypatch: Any) -> None:
    collection = FakeCollection()
    install_fake_pymongo(monkeypatch, collection)
    calls: list[dict[str, Any] | None] = []

    def fake_call_langflow_api(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs.get("tweaks"))
        if len(calls) == 1:
            return {
                "status": "ok",
                "answer_message": "first",
                "state": {
                    "current_data": {
                        "columns": ["MODE", "WIP"],
                        "rows": [{"MODE": "A", "WIP": 1}, {"MODE": "B", "WIP": 2}, {"MODE": "C", "WIP": 3}],
                        "row_count": 3,
                        "data_ref": {"store": "mongodb", "ref_id": "result-ref"},
                        "product_key_columns": ["MODE"],
                    },
                    "followup_source_results": [
                        {
                            "source_alias": "wip_data",
                            "dataset_key": "wip_today",
                            "data_ref": {"store": "mongodb", "ref_id": "source-ref"},
                            "row_count": 3,
                        }
                    ],
                },
            }
        return {
            "status": "ok",
            "answer_message": "second",
            "state": {"current_data": {"columns": ["MODE"], "rows": [{"MODE": "A"}], "row_count": 1}},
        }

    monkeypatch.setattr(langflow_client, "call_langflow_api", fake_call_langflow_api)
    settings = LangflowSettings(
        main_api_url="http://fake-main",
        session_store="mongodb",
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v2",
        session_state_collection="agent_v2_session_states",
        session_state_preview_row_limit=2,
    )
    client = LangflowApiClient(settings)

    first = client.run_query("first question", "session-1")
    stored_state = collection.docs["session_state:session-1"]["state"]
    second = client.run_query("second question", "session-1")

    assert calls[0] is None
    assert first["session_state_store"]["write"]["saved"] is True
    assert stored_state["current_data"]["rows"] == [{"MODE": "A", "WIP": 1}, {"MODE": "B", "WIP": 2}]
    assert stored_state["current_data"]["data_ref"]["ref_id"] == "result-ref"
    assert calls[1]["00 Request State Loader"]["state"]["current_data"]["data_ref"]["ref_id"] == "result-ref"
    assert second["session_state_store"]["load"]["loaded"] is True


def test_langflow_client_prefers_explicit_state_over_session_store(monkeypatch: Any) -> None:
    collection = FakeCollection()
    collection.docs["session_state:session-1"] = {
        "_id": "session_state:session-1",
        "session_id": "session-1",
        "state": {"current_data": {"rows": [{"MODE": "OLD"}], "row_count": 1}},
    }
    install_fake_pymongo(monkeypatch, collection)
    calls: list[dict[str, Any] | None] = []

    def fake_call_langflow_api(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs.get("tweaks"))
        return {"status": "ok", "answer_message": "ok", "state": {"current_data": {"row_count": 0}}}

    monkeypatch.setattr(langflow_client, "call_langflow_api", fake_call_langflow_api)
    settings = LangflowSettings(
        main_api_url="http://fake-main",
        session_store="mongodb",
        mongo_uri="mongodb://fake",
    )
    client = LangflowApiClient(settings)

    client.run_query("question", "session-1", state={"current_data": {"rows": [{"MODE": "NEW"}], "row_count": 1}})

    assert calls[0]["00 Request State Loader"]["state"]["current_data"]["rows"] == [{"MODE": "NEW"}]
