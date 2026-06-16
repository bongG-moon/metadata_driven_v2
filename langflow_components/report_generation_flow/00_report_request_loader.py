from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


def build_report_request(question: str, session_id: str = "demo-session", state: Any = None, router_payload: Any = None) -> dict[str, Any]:
    state_data = deepcopy(state.data) if hasattr(state, "data") and isinstance(state.data, dict) else deepcopy(state) if isinstance(state, dict) else {}
    router_data = (
        deepcopy(router_payload.data)
        if hasattr(router_payload, "data") and isinstance(router_payload.data, dict)
        else deepcopy(router_payload)
        if isinstance(router_payload, dict)
        else {}
    )
    return {
        "payload_version": "agent-v1",
        "status": "ok",
        "flow_type": "report_generation",
        "request": {"question": str(question or ""), "session_id": str(session_id or "demo-session")},
        "state": state_data,
        "router_payload": router_data,
        "report": {"status": "drafting", "sections": []},
        "warnings": [],
        "errors": [],
    }


class ReportRequestLoader(Component):
    display_name = "00 Report Request Loader"
    description = "Builds the report-generation flow payload from the routed user request."
    icon = "FileText"
    inputs = [
        MessageTextInput(name="question", display_name="Question", required=True),
        MessageTextInput(name="session_id", display_name="Session ID", value="demo-session"),
        DataInput(name="state", display_name="Previous State", required=False),
        DataInput(name="router_payload", display_name="Router Payload", required=False),
    ]
    outputs = [Output(name="payload", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        return Data(
            data=build_report_request(
                getattr(self, "question", ""),
                getattr(self, "session_id", "demo-session"),
                getattr(self, "state", None),
                getattr(self, "router_payload", None),
            )
        )
