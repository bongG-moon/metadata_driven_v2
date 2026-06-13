from __future__ import annotations

import json
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def build_table_catalog_authoring_prompt_payload(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    existing_summary = [
        {
            "dataset_key": item.get("dataset_key"),
            "display_name": item.get("display_name"),
            "dataset_family": item.get("dataset_family"),
            "date_scope": item.get("date_scope"),
            "source_type": item.get("source_type"),
            "columns": item.get("columns", [])[:12],
        }
        for item in payload.get("existing_items", [])[:80]
        if isinstance(item, dict)
    ]
    prompt = "\n".join(
        [
            "You convert a refined dataset description into MongoDB-storable table_catalog metadata.",
            "Return one strict JSON object only. Do not wrap it in markdown.",
            "Use only information present in the refined text. Put missing essentials in missing_information.",
            "Do not invent query_template, API URL, document ID, sheet name, DB key, or physical columns.",
            "",
            "Existing dataset summary for duplicate awareness:",
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
                            "dataset_key": "stable_dataset_key",
                            "payload": {
                                "display_name": "business display name",
                                "dataset_family": "production | wip | target | lot | hold | equipment | capacity | other",
                                "date_scope": "current_day | history | snapshot | optional",
                                "source_type": "dummy | oracle | h_api | datalake | goodocs",
                                "source_config": {
                                    "source_type": "same as source_type",
                                    "db_key": "required for oracle when known",
                                    "query_template": "required for oracle/datalake when known",
                                    "api_url": "required for h_api when known",
                                    "doc_id": "required for goodocs when known",
                                    "sheet_name": "required for goodocs when known",
                                },
                                "required_params": ["DATE"],
                                "required_param_mappings": {"DATE": ["WORK_DT"]},
                                "primary_quantity_column": "column or list",
                                "filter_mappings": {"DATE": ["WORK_DT"]},
                                "columns": ["physical columns"],
                            },
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
    return {"prompt": prompt, "payload": payload, "prompt_type": "table_catalog_authoring_json"}


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


class TableCatalogAuthoringPromptBuilder(Component):
    display_name = "03 Table Catalog Authoring Prompt Builder"
    description = "Builds the Gemini/LLM prompt that converts cleaned text into table catalog JSON."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="authoring_prompt", display_name="Authoring Prompt", method="build_prompt"),
        Output(name="prompt_payload", display_name="Prompt Payload", method="build_prompt_payload"),
    ]

    def build_prompt(self) -> Message:
        prompt_payload = build_table_catalog_authoring_prompt_payload(getattr(self, "payload", None))
        self.status = {"prompt_type": prompt_payload["prompt_type"], "chars": len(prompt_payload["prompt"])}
        return Message(text=prompt_payload["prompt"])

    def build_prompt_payload(self) -> Data:
        return Data(data=build_table_catalog_authoring_prompt_payload(getattr(self, "payload", None)))
