from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def build_request_payload(question: str, session_id: str = "demo-session", state: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "payload_version": "agent-v1",
        "status": "ok",
        "request": {"session_id": session_id, "question": question, "timezone": "Asia/Seoul"},
        "state": deepcopy(state or {"chat_history": [], "context": {}, "current_data": {}}),
        "info": [],
        "warnings": [],
        "errors": [],
    }



class RequestStateLoader(Component):
    display_name = "00 Request State Loader"
    description = "Builds the compact request payload from chat input and previous state."
    inputs = [
        MessageTextInput(name="question", display_name="Question", required=True),
        MessageTextInput(name="session_id", display_name="Session ID", value="demo-session"),
        DataInput(name="state", display_name="Previous State", required=False),
    ]
    outputs = [Output(name="payload", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        state = getattr(self.state, "data", self.state) if getattr(self, "state", None) else None
        payload = build_request_payload(self.question, self.session_id, state)
        return Data(data=payload)
