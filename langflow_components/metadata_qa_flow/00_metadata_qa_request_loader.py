from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


def build_metadata_qa_request(
    question: str,
    session_id: str = "demo-session",
    state: Any = None,
    metadata_route: Any = None,
    metadata: Any = None,
    router_payload: Any = None,
) -> dict[str, Any]:
    payload = {
        "payload_version": "agent-v1",
        "status": "ok",
        "request": {"session_id": str(session_id or "demo-session"), "question": str(question or ""), "timezone": "Asia/Seoul"},
        "state": _dict_value(state),
        "info": [],
        "warnings": [],
        "errors": [],
    }
    route = _dict_value(metadata_route)
    router = _dict_value(router_payload)
    if not route and isinstance(router.get("metadata_route"), dict):
        route = deepcopy(router["metadata_route"])
    if not route and isinstance(router.get("flow_inputs"), dict) and isinstance(router["flow_inputs"].get("metadata_route"), dict):
        route = deepcopy(router["flow_inputs"]["metadata_route"])
    if route:
        payload["metadata_route"] = route
    metadata_value = _dict_value(metadata)
    if not metadata_value and isinstance(router.get("flow_inputs"), dict) and isinstance(router["flow_inputs"].get("metadata"), dict):
        metadata_value = deepcopy(router["flow_inputs"]["metadata"])
    if metadata_value:
        payload["metadata"] = metadata_value
    if router:
        payload["router_payload"] = router
    return payload


def _dict_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


class MetadataQARequestLoader(Component):
    display_name = "00 Metadata QA Request Loader"
    description = "Builds the metadata-QA payload from router-selected question, state, and metadata_route."
    icon = "SearchCheck"
    inputs = [
        MessageTextInput(name="question", display_name="Question", required=True),
        MessageTextInput(name="session_id", display_name="Session ID", value="demo-session"),
        DataInput(name="state", display_name="Previous State", required=False),
        DataInput(name="metadata_route", display_name="Metadata Route", required=False),
        DataInput(name="metadata", display_name="Metadata", required=False),
        DataInput(name="router_payload", display_name="Router Payload", required=False),
    ]
    outputs = [Output(name="payload", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        payload = build_metadata_qa_request(
            getattr(self, "question", ""),
            getattr(self, "session_id", "demo-session"),
            getattr(self, "state", None),
            getattr(self, "metadata_route", None),
            getattr(self, "metadata", None),
            getattr(self, "router_payload", None),
        )
        self.status = {
            "route": (payload.get("metadata_route") or {}).get("route"),
            "metadata_action": (payload.get("metadata_route") or {}).get("metadata_action"),
        }
        return Data(data=payload)
