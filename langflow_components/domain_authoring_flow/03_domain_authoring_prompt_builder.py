from __future__ import annotations

import json
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def build_domain_authoring_prompt_payload(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    existing_summary = [
        {
            "section": item.get("section"),
            "key": item.get("key"),
            "aliases": item.get("aliases", [])[:8],
            "processes": item.get("processes", [])[:8],
            "columns": item.get("columns", [])[:8],
        }
        for item in payload.get("existing_items", [])[:80]
        if isinstance(item, dict)
    ]
    prompt = "\n".join(
        [
            "You convert a refined manufacturing domain description into MongoDB-storable domain metadata.",
            "Return one strict JSON object only. Do not wrap it in markdown.",
            "Use only information present in the refined text. Put missing essentials in missing_information.",
            "Prefer structured JSON conditions, for example {\"TSV_DIE_TYP\": {\"exists\": true, \"not_in\": [null, \"\"]}}.",
            "Use aggregation='nunique' for distinct LOT_ID counts. Do not use count_distinct.",
            "",
            "Existing domain item summary for duplicate awareness:",
            json.dumps(existing_summary, ensure_ascii=False, indent=2),
            "",
            "Refined text:",
            str(payload.get("refined_text") or payload.get("raw_text") or ""),
            "",
            "Required JSON schema:",
            json.dumps(
                {
                    "items": [
                        {
                            "section": "process_groups | product_terms | quantity_terms | metric_terms | status_terms | product_key_columns",
                            "key": "stable_key",
                            "payload": {
                                "display_name": "business display name",
                                "aliases": ["business words"],
                                "processes": ["optional for process_groups"],
                                "condition": {"optional": "structured condition"},
                                "dataset_key": "optional dataset key",
                                "dataset_family": "optional dataset family",
                                "quantity_column": "optional column",
                                "aggregation": "sum | nunique | mean | max | min",
                                "formula": "optional formula",
                                "calculation_rule": "optional rule",
                            },
                            "columns": ["only for product_key_columns"],
                            "confidence": "high | medium | low",
                        }
                    ],
                    "missing_information": [
                        {"field": "field name", "reason": "Korean reason", "example_user_input": "Korean example"}
                    ],
                    "warnings": ["Korean warning"],
                },
                ensure_ascii=False,
                indent=2,
            ),
        ]
    )
    return {"prompt": prompt, "payload": payload, "prompt_type": "domain_authoring_json"}


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


class DomainAuthoringPromptBuilder(Component):
    display_name = "03 Domain Authoring Prompt Builder"
    description = "Builds the Gemini/LLM prompt that converts cleaned text into domain metadata JSON."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="authoring_prompt", display_name="Authoring Prompt", method="build_prompt"),
        Output(name="prompt_payload", display_name="Prompt Payload", method="build_prompt_payload"),
    ]

    def build_prompt(self) -> Message:
        prompt_payload = build_domain_authoring_prompt_payload(getattr(self, "payload", None))
        self.status = {"prompt_type": prompt_payload["prompt_type"], "chars": len(prompt_payload["prompt"])}
        return Message(text=prompt_payload["prompt"])

    def build_prompt_payload(self) -> Data:
        return Data(data=build_domain_authoring_prompt_payload(getattr(self, "payload", None)))
