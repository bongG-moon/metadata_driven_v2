from __future__ import annotations

import importlib.util
import json
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


def test_langflow_llm_node_style_flow_contract(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/01_metadata_context_loader.py")
    intent_prompt_builder = load_component("langflow_components/main_flow/02_intent_prompt_builder.py")
    intent_normalizer = load_component("langflow_components/main_flow/03_intent_plan_normalizer.py")
    dummy_retriever = load_component("langflow_components/data_retrieval_flow/01_dummy_data_retriever.py")
    retrieval_adapter = load_component("langflow_components/main_flow/04_retrieval_payload_adapter.py")
    data_store = load_component("langflow_components/main_flow/05_mongodb_data_store.py")
    data_loader = load_component("langflow_components/main_flow/06_mongodb_data_loader.py")
    pandas_prompt_builder = load_component("langflow_components/main_flow/07_pandas_prompt_builder.py")
    pandas_executor = load_component("langflow_components/main_flow/08_pandas_code_executor.py")
    answer_prompt_builder = load_component("langflow_components/main_flow/09_answer_prompt_builder.py")
    answer_builder = load_component("langflow_components/main_flow/10_answer_response_builder.py")
    answer_message_adapter = load_component("langflow_components/main_flow/11_answer_message_adapter.py")

    payload = request_loader.build_request_payload("오늘 전체 재공 수량 알려줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)

    intent_prompt = intent_prompt_builder.build_intent_prompt_payload(payload)["prompt"]
    assert "Langflow Gemini/LLM node" in intent_prompt
    assert "Required JSON schema" in intent_prompt

    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "aggregate_wip_total",
        "datasets": ["wip_today"],
        "params_by_dataset": {"wip_today": {"DATE": "20260612"}},
        "filters": [],
        "retrieval_jobs": [
            {
                "dataset_key": "wip_today",
                "source_alias": "wip_total",
                "purpose": "current total WIP",
                "params": {"DATE": "20260612"},
                "filters": [],
                "required_columns": ["WORK_DT", "OPER_NAME", "WIP"],
            }
        ],
        "step_plan": [{"step_id": "sum_wip", "operation": "aggregate_sum", "source_alias": "wip_total"}],
        "depends_on_state": False,
        "reasoning_steps": ["Use current-day WIP and sum the WIP measure."],
    }
    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    assert payload["intent_plan"]["route"] == "single_retrieval"
    assert payload["retrieval_jobs"][0]["source_type"] == "oracle"

    retrieval_payload = dummy_retriever.retrieve_dummy_data(payload)
    payload = retrieval_adapter.adapt_retrieval_payload(payload, retrieval_payload)
    assert payload["runtime_sources"]["wip_total"]
    assert payload["source_results"][0]["preview_rows"]
    payload = data_store.store_payload_in_mongodb(payload, enabled="false")
    payload = data_loader.load_payload_from_mongodb(payload, enabled="false")

    pandas_prompt = pandas_prompt_builder.build_pandas_prompt_payload(payload)["prompt"]
    assert "result_df" in pandas_prompt
    assert "aggregate_wip_total" in pandas_prompt

    pandas_llm_json = {
        "code": "\n".join(
            [
                "df = sources['wip_total']",
                "result_df = pd.DataFrame([{'SCOPE': plan.get('scope_label', 'ALL'), 'WIP': int(df['WIP'].sum())}])",
            ]
        ),
        "output_columns": ["SCOPE", "WIP"],
        "reasoning_steps": ["Sum WIP from the current WIP source."],
    }
    payload = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))
    assert payload["analysis"]["safety_passed"] is True
    assert payload["analysis"]["executed"] is True
    assert payload["analysis"]["row_count"] == 1
    assert payload["analysis"]["rows"][0]["WIP"] > 0

    answer_prompt = answer_prompt_builder.build_answer_prompt_payload(payload)["prompt"]
    assert "Answer in Korean" in answer_prompt
    assert "wip_today" in answer_prompt

    answer_llm_json = {"answer_message": "오늘 전체 재공 수량은 계산 결과 기준으로 확인되었습니다."}
    payload = answer_builder.build_answer_response_payload(payload, json.dumps(answer_llm_json, ensure_ascii=False))
    payload = data_store.store_payload_in_mongodb(payload, enabled="false")
    assert payload["answer_message"] == answer_llm_json["answer_message"]
    assert payload["data"]["row_count"] == 1
    assert payload["applied_scope"]["datasets"] == ["wip_today"]
    assert "runtime_sources" not in payload
    assert payload["state"]["current_data"]["source_dataset_keys"] == ["wip_today"]

    playground_message = answer_message_adapter.build_playground_message(payload)
    assert "### 답변" in playground_message
    assert "### 결과 테이블" in playground_message
    assert "### 의도 분석" in playground_message
    assert "### Pandas 처리" in playground_message
    assert "| SCOPE | WIP |" in playground_message
    assert "aggregate_wip_total" in playground_message
    assert "```python" in playground_message


def test_intent_normalizer_builds_fallback_jobs_when_llm_omits_jobs(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 DA공정에서 재공, 생산량과 목표값 그리고 생산달성율을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "production_wip_target_rate",
        "datasets": ["production_today", "wip_today", "target"],
        "params_by_dataset": {"production_today": {"DATE": "20260612"}, "wip_today": {"DATE": "20260612"}},
        "reasoning_steps": ["Need production, WIP, and target values for DA."],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["intent_plan"]["route"] == "multi_retrieval"
    assert [job["source_alias"] for job in payload["retrieval_jobs"]] == [
        "production_today_1",
        "wip_today_2",
        "target_3",
    ]
    assert [job["source_type"] for job in payload["retrieval_jobs"]] == ["oracle", "oracle", "goodocs"]
    assert payload["intent_plan"]["step_plan"] == []
    assert any("fallback jobs" in item for item in payload["warnings"])
    assert not any("fallback step_plan" in item for item in payload["warnings"])


def test_intent_normalizer_does_not_default_specialized_datasets(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 생산달성율을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "production_wip_target_rate",
        "reasoning_steps": ["Need production, WIP, and target values."],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["retrieval_jobs"] == []
    assert payload["intent_plan"]["step_plan"] == []
    assert payload["intent_plan"]["route"] == "multi_retrieval"
    assert any("no LLM-provided datasets" in item for item in payload["warnings"])


def test_intent_normalizer_builds_generic_rank_fallback_step(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 재공 상위 3개 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "rank_top_n",
        "datasets": ["wip_today"],
        "top_n": 3,
        "reasoning_steps": ["Rank current WIP."],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert [job["source_alias"] for job in payload["retrieval_jobs"]] == ["wip_today"]
    assert payload["retrieval_jobs"][0]["params"]["DATE"] == "20260612"
    assert payload["retrieval_jobs"][0]["primary_quantity_column"] == "WIP"
    assert payload["intent_plan"]["step_plan"] == [
        {
            "step_id": "rank_items",
            "operation": "rank_top_n",
            "source_alias": "wip_today",
            "metric": "WIP",
            "top_n": 3,
            "rank_order": "desc",
        }
    ]
    assert any("generic fallback step_plan" in item for item in payload["warnings"])


def test_intent_normalizer_augments_existing_jobs_from_metadata(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 DA공정에서 재공, 생산량과 목표값 그리고 생산달성율을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "production_wip_target_rate",
        "datasets": ["production_today", "wip_today", "target"],
        "retrieval_jobs": [
            {"dataset_key": "production_today", "source_alias": "prod", "filters": [], "params": {}},
            {"dataset_key": "wip_today", "source_alias": "wip", "filters": [], "params": {}},
            {"dataset_key": "target", "source_alias": "target", "filters": [], "params": {}},
        ],
        "step_plan": [{"step_id": "join", "operation": "join"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    jobs = {job["dataset_key"]: job for job in payload["retrieval_jobs"]}

    assert jobs["production_today"]["params"]["DATE"] == "20260612"
    assert jobs["wip_today"]["params"]["DATE"] == "20260612"
    assert _filter_values(jobs["production_today"], "DATE") == ["20260612"]
    assert _filter_values(jobs["wip_today"], "DATE") == ["20260612"]
    assert _filter_values(jobs["target"], "DATE") == ["2026-06-12"]
    assert _filter_values(jobs["production_today"], "OPER_NAME") == ["D/A1", "D/A2", "D/A3", "D/A4", "D/A5", "D/A6"]
    assert {"TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"}.issubset(
        set(jobs["production_today"]["required_columns"])
    )
    assert {"TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"}.issubset(
        set(jobs["target"]["required_columns"])
    )
    assert any("metadata-derived params/filters" in item for item in payload["warnings"])


def test_intent_normalizer_uses_product_terms_for_existing_jobs(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 LPDDR5 W/B 공정 재공과 생산량을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "aggregate_join",
        "datasets": ["production_today", "wip_today"],
        "retrieval_jobs": [
            {"dataset_key": "production_today", "source_alias": "prod", "filters": [], "params": {}},
            {"dataset_key": "wip_today", "source_alias": "wip", "filters": [], "params": {}},
        ],
        "step_plan": [{"step_id": "join", "operation": "join"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    job = payload["retrieval_jobs"][0]

    assert _filter_values(job, "MODE") == ["LPDDR5"]
    assert _filter_values(job, "OPER_NAME") == ["W/B1", "W/B2", "W/B3", "W/B4", "W/B5", "W/B6"]


def test_intent_normalizer_replaces_wrong_product_alias_filter_with_metadata_condition(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("HBM 제품의 장비 모델별 현황을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "equipment_by_model",
        "datasets": ["equipment_status"],
        "retrieval_jobs": [
            {
                "dataset_key": "equipment_status",
                "source_alias": "equipment",
                "filters": [{"field": "TECH", "op": "eq", "value": "HBM"}],
                "params": {},
            }
        ],
        "step_plan": [{"step_id": "by_model", "operation": "group_by"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    job = payload["retrieval_jobs"][0]

    assert _filter_values(job, "PKG_TYPE1") == ["HBM"]
    assert _filter_values(job, "TECH") == []


def test_intent_normalizer_aligns_followup_equipment_to_state_products(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("그 제품에 물려 있는 장비를 보여줘", "test-session")
    payload["state"] = {
        "current_data": {
            "rows": [
                {"TECH": "FC", "DEN": "128G", "MODE": "LPDDR5", "PKG_TYPE1": "UFBGA", "MCP_NO": "EMPTY"}
            ]
        }
    }
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "followup_transform",
        "analysis_kind": "equipment_by_model",
        "datasets": ["equipment_status"],
        "retrieval_jobs": [
            {"dataset_key": "equipment_status", "source_alias": "equipment", "filters": [], "params": {}}
        ],
        "step_plan": [{"step_id": "equipment", "operation": "detail_rows"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]

    assert plan["analysis_kind"] == "equipment_for_previous_products"
    assert plan["state_product_keys"] == [
        {"TECH": "FC", "DEN": "128G", "MODE": "LPDDR5", "PKG_TYPE1": "UFBGA", "MCP_NO": "EMPTY"}
    ]
    assert any(item.get("field") == "PRODUCT_GRAIN" for item in payload["retrieval_jobs"][0]["filters"])


def test_intent_normalizer_maps_logical_required_columns_to_dataset_columns(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("현재 작업대기 Lot 수량을 공정별로 알려줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "lot_count_by_process",
        "datasets": ["lot_status"],
        "filters": [{"field": "LOT_STAT_CD", "op": "in", "values": ["WAITING"]}],
        "retrieval_jobs": [
            {
                "dataset_key": "lot_status",
                "source_alias": "lot_status_data",
                "required_columns": ["OPER_NAME", "LOT_ID", "LOT_STAT_CD"],
                "filters": [{"field": "LOT_STAT_CD", "op": "in", "values": ["WAITING"]}],
            }
        ],
        "step_plan": [
            {
                "step_id": "aggregate_waiting_lots",
                "operation": "group_by_count_unique",
                "source_alias": "lot_status_data",
                "group_by_columns": ["OPER_NAME"],
                "count_column": "LOT_ID",
            }
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    job = payload["retrieval_jobs"][0]

    assert "OPER_SHORT_DESC" in job["required_columns"]
    assert "LOT_ID" in job["required_columns"]
    assert "WF_QTY" in job["required_columns"]
    assert payload["intent_plan"]["step_plan"][0]["group_by_columns"] == ["OPER_SHORT_DESC"]


def test_intent_normalizer_adds_primary_quantity_to_equipment_columns(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 HBM 장비 보유 현황을 EQP_MODEL별로 알려줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "equipment_by_model",
        "datasets": ["equipment_status"],
        "retrieval_jobs": [
            {
                "dataset_key": "equipment_status",
                "source_alias": "equipment_data",
                "required_columns": ["EQP_MODEL", "EQPID"],
                "filters": [{"field": "PKG_TYPE1", "op": "eq", "value": "HBM"}],
            }
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["retrieval_jobs"][0]["required_columns"] == ["EQP_MODEL", "EQPID", "PRESS_CNT"]


def test_pandas_executor_normalizes_llm_result_column_names() -> None:
    pandas_executor = load_component("langflow_components/main_flow/08_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "rank_wip_then_join_production",
            "product_grain": ["MODE"],
        },
        "state": {},
        "runtime_sources": {},
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "result_df = pd.DataFrame([",
                "    {'RANK_GROUP': 'DA', 'MODE': 'LPDDR5', 'WIP_sum': 10, 'rank': 1, 'PRODUCTION_sum': 7}",
                "])",
            ]
        ),
        "output_columns": ["RANK_GROUP", "MODE", "WIP_sum", "rank", "PRODUCTION_sum"],
        "reasoning_steps": ["Return a ranked aggregate row."],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["columns"] == ["RANK_GROUP", "WIP_RANK", "MODE", "WIP", "PRODUCTION"]
    assert result["analysis"]["rows"][0]["WIP_RANK"] == 1
    assert result["analysis"]["rows"][0]["PRODUCTION"] == 7


def test_pandas_executor_normalizes_common_result_aliases() -> None:
    pandas_executor = load_component("langflow_components/main_flow/08_pandas_code_executor.py")
    aggregate_payload = {
        "intent_plan": {"analysis_kind": "aggregate_wip_total", "scope_label": "DA"},
        "state": {},
        "runtime_sources": {},
    }
    aggregate_llm_json = {
        "code": "result_df = pd.DataFrame([{'TOTAL_WIP': 42}])",
        "output_columns": ["TOTAL_WIP"],
        "reasoning_steps": [],
    }

    aggregate_result = pandas_executor.execute_pandas_from_llm(
        aggregate_payload, json.dumps(aggregate_llm_json, ensure_ascii=False)
    )

    assert aggregate_result["analysis"]["columns"] == ["SCOPE", "WIP"]
    assert aggregate_result["analysis"]["rows"][0] == {"SCOPE": "DA", "WIP": 42}

    lot_payload = {
        "intent_plan": {"analysis_kind": "lot_quantity_summary"},
        "state": {},
        "runtime_sources": {},
    }
    lot_llm_json = {
        "code": "result_df = pd.DataFrame([{'LOT_COUNT': 3, 'WAFER_QTY': 12, 'DIE_QTY': 90}])",
        "output_columns": ["LOT_COUNT", "WAFER_QTY", "DIE_QTY"],
        "reasoning_steps": [],
    }

    lot_result = pandas_executor.execute_pandas_from_llm(lot_payload, json.dumps(lot_llm_json, ensure_ascii=False))

    assert lot_result["analysis"]["columns"] == ["LOT_COUNT", "WF_QTY", "DIE_QTY"]
    assert lot_result["analysis"]["rows"][0]["WF_QTY"] == 12


def test_answer_message_adapter_escapes_tilde_strikethrough_markdown() -> None:
    answer_message_adapter = load_component("langflow_components/main_flow/11_answer_message_adapter.py")
    payload = {
        "answer_message": "결과는 ~~HOLD~~ 상태로 표시됩니다.",
        "data": {
            "columns": ["STATUS"],
            "rows": [{"STATUS": "~~HOLD~~"}],
            "row_count": 1,
        },
    }

    message = answer_message_adapter.build_playground_message(payload)

    assert "\\~\\~HOLD\\~\\~" in message
    assert "~~HOLD~~" not in message


def load_seed_metadata_payload(module: Any, payload: dict[str, Any], monkeypatch: Any) -> dict[str, Any]:
    install_fake_pymongo(monkeypatch, seed_metadata_docs())
    return module.load_metadata_payload(
        payload,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v2",
        domain_collection_name="agent_v2_domain_items",
        table_catalog_collection_name="agent_v2_table_catalog_items",
        main_flow_filter_collection_name="agent_v2_main_flow_filters",
    )


def seed_metadata_docs() -> dict[str, list[dict[str, Any]]]:
    domain = read_metadata_json("domain_items.json")
    table_catalog = read_metadata_json("table_catalog.json")
    filters = read_metadata_json("main_flow_filters.json")
    domain_docs: list[dict[str, Any]] = []
    for section, value in domain.items():
        if section == "product_key_columns":
            domain_docs.append({"section": section, "key": section, "columns": value})
        elif isinstance(value, dict):
            for key, payload in value.items():
                domain_docs.append({"section": section, "key": key, "payload": payload})
    table_docs = [
        {"dataset_key": key, "payload": payload}
        for key, payload in (table_catalog.get("datasets") or {}).items()
    ]
    filter_docs = [{"filter_key": key, "payload": payload} for key, payload in filters.items()]
    return {
        "agent_v2_domain_items": domain_docs,
        "agent_v2_table_catalog_items": table_docs,
        "agent_v2_main_flow_filters": filter_docs,
    }


def read_metadata_json(filename: str) -> dict[str, Any]:
    return json.loads((ROOT / "metadata" / filename).read_text(encoding="utf-8"))


def _filter_values(job: dict[str, Any], field: str) -> list[Any]:
    values: list[Any] = []
    for item in job.get("filters", []):
        if not isinstance(item, dict) or item.get("field") != field:
            continue
        if "value" in item:
            values.append(item["value"])
        if isinstance(item.get("values"), list):
            values.extend(item["values"])
    return values


class FakeCursor(list):
    def limit(self, value: int) -> "FakeCursor":
        return FakeCursor(self[:value])


class FakeCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs

    def find(self, query: dict[str, Any]) -> FakeCursor:
        return FakeCursor(self.docs)


class FakeDatabase:
    def __init__(self, docs_by_collection: dict[str, list[dict[str, Any]]]) -> None:
        self.docs_by_collection = docs_by_collection

    def __getitem__(self, collection_name: str) -> FakeCollection:
        return FakeCollection(self.docs_by_collection.get(collection_name, []))


class FakeClient:
    def __init__(self, docs_by_collection: dict[str, list[dict[str, Any]]]) -> None:
        self.docs_by_collection = docs_by_collection

    def __getitem__(self, database_name: str) -> FakeDatabase:
        return FakeDatabase(self.docs_by_collection)

    def close(self) -> None:
        return None


def install_fake_pymongo(monkeypatch: Any, docs_by_collection: dict[str, list[dict[str, Any]]]) -> None:
    def mongo_client(*args: Any, **kwargs: Any) -> FakeClient:
        return FakeClient(docs_by_collection)

    monkeypatch.setitem(sys.modules, "pymongo", types.SimpleNamespace(MongoClient=mongo_client))
