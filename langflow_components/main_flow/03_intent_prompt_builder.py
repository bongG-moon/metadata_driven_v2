from __future__ import annotations

import json
from copy import deepcopy
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
            "Resolve product/status words through domain metadata product_terms/status_terms before choosing filters.",
            "Resolve metric words through domain metadata metric_terms and quantity_terms before choosing datasets.",
            "Use domain metadata analysis_recipes when the question matches a known analysis pattern.",
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
                    "product_grain": ["columns used for product/process grouping, or [] for total/detail rows"],
                    "metric": "standard metric column for ranking/aggregation, such as WIP or PRODUCTION",
                    "top_n": "positive integer for top/rank questions",
                    "rank_order": "desc | asc",
                    "analysis_output_columns": ["standard result columns expected after pandas, optional"],
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
                    "step_plan": [
                        {
                            "step_id": "short id",
                            "operation": "analysis operation",
                            "source_alias": "source alias",
                            "metric": "optional metric column",
                            "top_n": "optional positive integer",
                            "rank_order": "optional desc|asc",
                            "group_by": ["optional grouping columns"],
                            "output_columns": ["optional standard result columns"],
                        }
                    ],
                    "depends_on_state": False,
                    "requires_full_state_hydrate": False,
                    "state_hydrate_mode": "summary | full",
                    "reasoning_steps": ["short Korean or English reasoning step"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            "",
            "Rules:",
            "- Use intent_type=detail_lookup for detail row requests such as a specific LOT hold history or hold lot list.",
            "- If the user asks for 상세 데이터, 세부 데이터, 원본 row, 전체 row, or says not to aggregate/group, preserve source rows with analysis_kind=detail_rows instead of forcing group_by.",
            "- Use intent_type=single_retrieval_analysis for one-dataset aggregation/ranking questions.",
            "- Use intent_type=multi_source_analysis for questions that need multiple datasets.",
            "- Use intent_type=multi_step_analysis when one step creates keys that the next step must reuse.",
            "- If analysis_kind=rank_wip_then_join_production, intent_type must be multi_step_analysis.",
            "- Always return retrieval_jobs for every dataset in datasets unless intent_type=finish. Do not return only datasets/params/filters.",
            "- Always return step_plan for analysis requests unless intent_type=finish. The step_plan must say which operation uses which source_alias.",
            "- Use intent_type=followup_transform when the question says 이 제품/그 제품/해당 제품 and needs previous state.",
            "- For follow-up questions that recalculate, filter, sort, regroup, or show detail rows from the previous result itself, set requires_full_state_hydrate=true and state_hydrate_mode=full.",
            "- For follow-up questions that only need previous product keys for a new retrieval, keep state_hydrate_mode=summary.",
            "- For 오늘/현재, prefer datasets whose metadata date_scope is current_day unless the question asks for history.",
            "- For 목표/계획, use dataset families and quantity/metric terms from metadata, and preserve each dataset's date_format.",
            "- For status or detail requests, use status_terms and table_catalog metadata instead of hardcoded status codes.",
            "- For top/bottom/rank questions, do not return a nested rank object. Put ranking values in top-level metric/top_n/rank_order and repeat them in the rank step_plan item.",
            "- For 가장 많은/most/highest/top questions without an explicit count, use top_n=1 and rank_order=desc.",
            "- For top/bottom/rank questions followed by a dependent lookup, express rank first and dependent retrieval/analysis steps second.",
            "- Do not use loose top-level group_by/output_columns as substitutes for step_plan. Use product_grain and analysis_output_columns, and include group_by/output_columns inside the relevant step when needed.",
            "- Use aggregate_wip_total only for one-dataset total/sum questions that metadata identifies as WIP/current quantity work.",
            "- Use aggregate_join only for a simple multi-source join when no matching analysis_recipes item gives a more specific plan.",
            "- If an analysis_recipes item matches the question, use its required_quantity_terms, required_dataset_families, metric_terms, grain_policy, source_aliases_by_family, defaults, and output_columns as planning evidence.",
            "- grain_policy decides grouping: aggregate_total means one total row; question_or_product_grain means use the grain explicitly requested by the question, otherwise use the product grain only when product-level rows are natural.",
            "- If a required dataset, filter, formula, or value mapping is not present in metadata, do not hardcode it. Return the closest metadata-backed plan and explain the missing item in reasoning_steps.",
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
        "product_terms": domain.get("product_terms", {}),
        "quantity_terms": domain.get("quantity_terms", {}),
        "metric_terms": domain.get("metric_terms", {}),
        "analysis_recipes": domain.get("analysis_recipes", {}),
        "status_terms": domain.get("status_terms", {}),
        "product_key_columns": domain.get("product_key_columns", []),
        "datasets": datasets,
    }


def _state_summary(state: dict[str, Any]) -> dict[str, Any]:
    current_data = state.get("current_data") if isinstance(state.get("current_data"), dict) else {}
    rows = _rows_from_current_data(current_data)
    return {
        "has_state": bool(state),
        "context": state.get("context", {}),
        "current_data_columns": current_data.get("columns", []),
        "current_data_row_count": current_data.get("row_count", 0),
        "current_data_preview_rows": rows[:3],
        "current_data_product_key_columns": current_data.get("product_key_columns", []),
        "current_data_product_key_values": _list_preview(current_data.get("product_key_values"), 20),
        "current_data_product_key_count": current_data.get("product_key_count", 0),
        "followup_source_results": state.get("followup_source_results", []),
    }


def _rows_from_current_data(current_data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = current_data.get("rows")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    data = current_data.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        return [row for row in data["rows"] if isinstance(row, dict)]
    return []


def _list_preview(value: Any, limit: int) -> list[Any]:
    return deepcopy(value[:limit]) if isinstance(value, list) else []


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


class IntentPromptBuilder(Component):
    display_name = "03 Intent Prompt Builder"
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
