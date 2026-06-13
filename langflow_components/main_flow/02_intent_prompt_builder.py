from __future__ import annotations

import json
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


SUPPORTED_ANALYSIS_KINDS = [
    "rank_wip_then_join_production",
    "detail_rows",
    "rank_top_n",
    "equipment_for_previous_products",
    "aggregate_join",
    "production_wip_target_rate",
    "low_output_vs_target",
    "lot_count_by_process",
    "lot_quantity_summary",
    "aggregate_wip_total",
    "overall_production_wip_target",
    "date_split_production_plan_gap",
    "equipment_by_model",
    "none",
]


def build_intent_prompt_payload(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    question = str((payload.get("request") or {}).get("question") or "")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    request_date = str((payload.get("request") or {}).get("date") or "20260612")
    prompt = "\n".join(
        [
            "You are the intent planning node for a metadata-driven manufacturing data agent.",
            "This prompt will be sent to a Langflow Gemini/LLM node, and that node must return the intent JSON.",
            "Return one strict JSON object only. Do not wrap it in markdown.",
            "Think like a manufacturing analyst: split complex questions into ordered data/analysis steps.",
            "Use the provided metadata. Do not invent dataset keys or filter fields.",
            "",
            "Current date parameter:",
            request_date,
            "",
            "Supported analysis_kind values:",
            json.dumps(SUPPORTED_ANALYSIS_KINDS, ensure_ascii=False),
            "",
            "Metadata summary:",
            json.dumps(_metadata_summary(metadata), ensure_ascii=False, indent=2),
            "",
            "Previous state summary:",
            json.dumps(_state_summary(state), ensure_ascii=False, indent=2),
            "",
            "User question:",
            question,
            "",
            "Required JSON schema:",
            json.dumps(
                {
                    "intent_type": "single_retrieval_analysis | multi_source_analysis | multi_step_analysis | detail_lookup | followup_transform | finish",
                    "analysis_kind": "one supported analysis_kind",
                    "datasets": ["dataset_key"],
                    "params_by_dataset": {"dataset_key": {"DATE": "YYYYMMDD or YYYY-MM-DD", "LOT_ID": "optional"}},
                    "filters": [{"field": "metadata filter field", "op": "eq|in|not_empty|tuple_in", "value": "optional", "values": []}],
                    "retrieval_jobs": [
                        {
                            "dataset_key": "dataset key from metadata",
                            "source_alias": "short unique alias",
                            "purpose": "why this data is needed",
                            "params": {},
                            "filters": [],
                            "required_columns": [],
                        }
                    ],
                    "step_plan": [{"step_id": "short id", "operation": "analysis operation", "source_alias": "source alias"}],
                    "depends_on_state": False,
                    "reasoning_steps": ["short Korean or English reasoning step"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            "",
            "Rules:",
            "- Use intent_type=detail_lookup for detail row requests such as a specific LOT hold history or hold lot list.",
            "- Use intent_type=single_retrieval_analysis for one-dataset aggregation/ranking questions.",
            "- Use intent_type=multi_source_analysis for questions that need multiple datasets.",
            "- Use intent_type=multi_step_analysis when one step creates keys that the next step must reuse.",
            "- If analysis_kind=rank_wip_then_join_production, intent_type must be multi_step_analysis.",
            "- Use intent_type=followup_transform when the question says 이 제품/그 제품/해당 제품 and needs previous state.",
            "- Use current-day datasets production_today and wip_today for 오늘/현재 unless the question asks 어제/history.",
            "- Use target for 목표/계획. target DATE format is YYYY-MM-DD.",
            "- For 작업대기 Lot 수량 use lot_status, LOT_STAT_CD=WAITING, and LOT_ID nunique.",
            "- For HOLD history of a specific lot use hold_history with LOT_ID.",
            "- For DA/WB each top WIP then production, express rank first and dependent production join steps.",
            "- If a question asks 재공 + 생산량 + 목표값/계획 + 달성율, set analysis_kind=production_wip_target_rate.",
            "- If a question asks 목표값 대비/계획 대비/INPUT계획대비 and low/저조 production, set analysis_kind=low_output_vs_target.",
            "- If a question asks only total/overall/current WIP or 재공 수량, set analysis_kind=aggregate_wip_total and use only wip_today.",
            "- If a question asks today's total production/wip/target values without product or process group-by, set analysis_kind=overall_production_wip_target.",
            "- Use overall_production_wip_target only when production, WIP, and target/plan are all requested together.",
            "- If a question asks yesterday production versus today's production plan gap, set analysis_kind=date_split_production_plan_gap.",
            "- Use aggregate_join only for a simple multi-source product-grain join with no target, rate, low-output, date-split, or lot quantity logic.",
        ]
    )
    return {"prompt": prompt, "payload": payload, "prompt_type": "intent"}


def _metadata_summary(metadata: dict[str, Any]) -> dict[str, Any]:
    table_catalog = metadata.get("table_catalog") if isinstance(metadata.get("table_catalog"), dict) else {}
    datasets = {}
    for key, item in (table_catalog.get("datasets") or {}).items():
        if not isinstance(item, dict):
            continue
        datasets[key] = {
            "family": item.get("dataset_family"),
            "date_scope": item.get("date_scope", ""),
            "source_type": item.get("source_type"),
            "required_params": item.get("required_params", []),
            "quantity": item.get("primary_quantity_column"),
            "filter_fields": sorted((item.get("filter_mappings") or {}).keys()),
            "columns": item.get("columns", []),
        }
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    return {
        "process_groups": domain.get("process_groups", {}),
        "quantity_terms": domain.get("quantity_terms", {}),
        "status_terms": domain.get("status_terms", {}),
        "product_key_columns": domain.get("product_key_columns", []),
        "datasets": datasets,
    }


def _state_summary(state: dict[str, Any]) -> dict[str, Any]:
    current_data = state.get("current_data") if isinstance(state.get("current_data"), dict) else {}
    rows = current_data.get("rows") if isinstance(current_data.get("rows"), list) else []
    return {
        "has_state": bool(state),
        "context": state.get("context", {}),
        "current_data_columns": current_data.get("columns", []),
        "current_data_preview_rows": rows[:3],
        "followup_source_results": state.get("followup_source_results", []),
    }


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


class IntentPromptBuilder(Component):
    display_name = "02 Intent Prompt Builder"
    description = "Builds the prompt that should be sent to the Langflow Gemini/LLM node for intent planning."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="intent_prompt", display_name="Intent Prompt", method="build_prompt"),
        Output(name="prompt_payload", display_name="Prompt Payload", method="build_prompt_payload"),
    ]

    def build_prompt(self) -> Message:
        prompt_payload = build_intent_prompt_payload(getattr(self, "payload", None))
        self.status = {"prompt_type": "intent", "chars": len(prompt_payload["prompt"])}
        return Message(text=prompt_payload["prompt"])

    def build_prompt_payload(self) -> Data:
        return Data(data=build_intent_prompt_payload(getattr(self, "payload", None)))
