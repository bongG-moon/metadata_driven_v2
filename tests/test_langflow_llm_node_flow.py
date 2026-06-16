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
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_prompt_builder = load_component("langflow_components/main_flow/03_intent_prompt_builder.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")
    dummy_retriever = load_component("langflow_components/data_retrieval_flow/01_dummy_data_retriever.py")
    retrieval_adapter = load_component("langflow_components/main_flow/05_retrieval_payload_adapter.py")
    data_store = load_component("langflow_components/main_flow/08_mongodb_data_store.py")
    data_loader = load_component("langflow_components/main_flow/01_mongodb_data_loader.py")
    pandas_prompt_builder = load_component("langflow_components/main_flow/06_pandas_prompt_builder.py")
    pandas_executor = load_component("langflow_components/main_flow/07_pandas_code_executor.py")
    answer_prompt_builder = load_component("langflow_components/main_flow/09_answer_prompt_builder.py")
    answer_builder = load_component("langflow_components/main_flow/10_answer_response_builder.py")
    answer_message_adapter = load_component("langflow_components/main_flow/11_answer_message_adapter.py")

    payload = request_loader.build_request_payload("오늘 전체 재공 수량 알려줘", "test-session")
    payload = data_loader.load_payload_from_mongodb(payload, enabled="false")
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

    payload = data_store.store_payload_in_mongodb(payload, enabled="false")
    answer_prompt = answer_prompt_builder.build_answer_prompt_payload(payload)["prompt"]
    assert "Answer in Korean" in answer_prompt
    assert "wip_today" in answer_prompt

    answer_llm_json = {"answer_message": "오늘 전체 재공 수량은 계산 결과 기준으로 확인되었습니다."}
    payload = answer_builder.build_answer_response_payload(payload, json.dumps(answer_llm_json, ensure_ascii=False))
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


def test_intent_normalizer_builds_recipe_jobs_when_llm_omits_jobs(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

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
    assert payload["intent_plan"]["matched_analysis_recipe"] == "production_wip_target_rate"
    assert [job["source_alias"] for job in payload["retrieval_jobs"]] == [
        "production_data",
        "wip_data",
        "target_data",
    ]
    assert [job["source_type"] for job in payload["retrieval_jobs"]] == ["oracle", "oracle", "goodocs"]
    assert payload["intent_plan"]["step_plan"][0]["recipe_key"] == "production_wip_target_rate"
    assert payload["intent_plan"]["step_plan"][0]["group_by"] == [
        "TECH",
        "DEN",
        "MODE",
        "PKG_TYPE1",
        "PKG_TYPE2",
        "LEAD",
        "MCP_NO",
    ]
    assert any("분석 recipe 'production_wip_target_rate'" in item for item in payload["info"])
    assert not any("분석 recipe 'production_wip_target_rate'" in item for item in payload["warnings"])
    assert not any("fallback jobs" in item for item in payload["warnings"])
    assert not any("fallback step_plan" in item for item in payload["warnings"])


def test_intent_normalizer_builds_recipe_jobs_when_llm_omits_specialized_datasets(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 생산달성율을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "production_wip_target_rate",
        "reasoning_steps": ["Need production, WIP, and target values."],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["intent_plan"]["matched_analysis_recipe"] == "production_wip_target_rate"
    assert payload["intent_plan"]["analysis_kind"] == "production_wip_target_rate"
    assert [job["dataset_key"] for job in payload["retrieval_jobs"]] == ["production_today", "wip_today", "target"]
    assert payload["intent_plan"]["step_plan"][0]["recipe_key"] == "production_wip_target_rate"
    assert payload["intent_plan"]["route"] == "multi_retrieval"
    assert any("분석 recipe 'production_wip_target_rate'" in item for item in payload["info"])
    assert not any("분석 recipe 'production_wip_target_rate'" in item for item in payload["warnings"])


def test_intent_normalizer_does_not_build_specialized_jobs_without_recipe_metadata(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 생산달성율을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    payload["metadata"]["domain_items"]["analysis_recipes"] = {}
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "production_wip_target_rate",
        "reasoning_steps": ["Need production, WIP, and target values."],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["retrieval_jobs"] == []
    assert payload["intent_plan"]["step_plan"] == []
    assert any("datasets도 없어 조회 작업을 보완할 수 없습니다" in item for item in payload["warnings"])


def test_intent_normalizer_recipe_grain_policy_uses_question_scope(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 전체 생산달성율을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "production_wip_target_rate",
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["intent_plan"]["matched_analysis_recipe"] == "production_wip_target_rate"
    assert payload["intent_plan"]["product_grain"] == []
    assert payload["intent_plan"]["step_plan"][0]["group_by"] == []


def test_intent_normalizer_detail_request_overrides_recipe_grouping(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload(
        "오늘 DA공정에서 재공, 생산량과 목표값 세부 데이터를 집계하지 말고 보여줘",
        "test-session",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "production_wip_target_rate",
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["intent_plan"]["matched_analysis_recipe"] == "production_wip_target_rate"
    assert payload["intent_plan"]["detail_rows_requested"] is True
    assert payload["intent_plan"]["analysis_kind"] == "detail_rows"
    assert payload["intent_plan"]["original_analysis_kind"] == "production_wip_target_rate"
    assert payload["intent_plan"]["product_grain"] == []
    assert [job["dataset_key"] for job in payload["retrieval_jobs"]] == ["production_today", "wip_today", "target"]
    assert payload["intent_plan"]["step_plan"] == [
        {
            "step_id": "detail_rows",
            "operation": "detail_rows",
            "source_alias": "production_data",
            "source_aliases": ["production_data", "wip_data", "target_data"],
        }
    ]
    assert "group_by" not in payload["intent_plan"]["step_plan"][0]
    assert "OPER_NAME" in payload["retrieval_jobs"][0]["required_columns"]
    assert "PRODUCTION" in payload["retrieval_jobs"][0]["required_columns"]


def test_intent_normalizer_recipe_defaults_populate_plan(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 INPUT계획대비 D/A공정에서 생산량이 저조한 제품을 알려줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "low_output_vs_target",
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["intent_plan"]["matched_analysis_recipe"] == "low_output_vs_target"
    assert payload["intent_plan"]["production_column"] == "PRODUCTION"
    assert payload["intent_plan"]["target_column"] == "INPUT_PLAN"
    assert payload["intent_plan"]["threshold"] == 1.0


def test_intent_normalizer_recipe_promotes_generic_lot_quantity_plan(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload(
        "현재 DA공정에서 재공 lot이 몇개인지, wafer가 몇개인지, die수량은 몇개인지 알려줘",
        "test-session",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "aggregate_join",
        "datasets": ["lot_status"],
        "retrieval_jobs": [
            {
                "dataset_key": "lot_status",
                "source_alias": "lot_data",
                "filters": [{"field": "OPER_NAME", "op": "in", "values": ["D/A1"]}],
                "required_columns": ["LOT_ID", "OPER_NAME", "WF_QTY", "SUB_PROD_QTY"],
            }
        ],
        "step_plan": [{"step_id": "aggregate_lot_quantities", "operation": "aggregate", "source_alias": "lot_data"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["intent_plan"]["matched_analysis_recipe"] == "lot_quantity_summary"
    assert payload["intent_plan"]["analysis_kind"] == "lot_quantity_summary"
    assert [job["dataset_key"] for job in payload["retrieval_jobs"]] == ["lot_status"]
    assert {"LOT_ID", "WF_QTY", "SUB_PROD_QTY"}.issubset(set(payload["retrieval_jobs"][0]["required_columns"]))


def test_intent_normalizer_recipe_aligns_history_dataset_for_date_split(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("어제 생산량과 오늘 생산계획의 차이수량을 제품별로 알려줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "date_split_production_plan_gap",
        "datasets": ["production_today", "target"],
        "params_by_dataset": {
            "production_today": {"DATE": "20260611"},
            "target": {"DATE": "20260612"},
        },
        "retrieval_jobs": [
            {"dataset_key": "production_today", "source_alias": "production_data", "params": {"DATE": "20260611"}},
            {"dataset_key": "target", "source_alias": "target_data", "params": {"DATE": "20260612"}},
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["intent_plan"]["matched_analysis_recipe"] == "date_split_production_plan_gap"
    assert [job["dataset_key"] for job in payload["retrieval_jobs"]] == ["production", "target"]
    assert payload["intent_plan"]["datasets"] == ["production", "target"]
    assert "production_today" not in payload["intent_plan"]["params_by_dataset"]
    assert payload["intent_plan"]["params_by_dataset"]["production"]["DATE"] == "20260611"
    assert any("dataset family" in item and "정렬" in item for item in payload["info"])
    assert not any("dataset family" in item and "정렬" in item for item in payload["warnings"])


def test_intent_normalizer_builds_generic_rank_fallback_step(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

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
    product_keys = payload["metadata"]["domain_items"]["product_key_columns"]

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
            "group_by": product_keys,
        }
    ]
    assert any("step_plan이 없어" in item for item in payload["info"])
    assert not any("step_plan이 없어" in item for item in payload["warnings"])


def test_intent_normalizer_absorbs_loose_rank_fields_before_fallback(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("현재 DA공정에서 재공이 가장 많은 제품 알려줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    product_keys = payload["metadata"]["domain_items"]["product_key_columns"]
    output_columns = [*product_keys, "WIP"]
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "rank_top_n",
        "datasets": ["wip_today"],
        "params_by_dataset": {"wip_today": {"DATE": "20260612"}},
        "filters": [{"field": "OPER_NAME", "op": "in", "values": ["D/A1", "D/A2", "D/A3", "D/A4", "D/A5", "D/A6"]}],
        "rank": {
            "quantity_column": "WIP",
            "rank_column": "WIP",
            "sort_order": "desc",
            "top_n": 1,
        },
        "group_by": product_keys,
        "output_columns": output_columns,
        "reasoning_steps": ["Rank DA WIP by product and return the largest product."],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]
    step = plan["step_plan"][0]

    assert plan["metric"] == "WIP"
    assert plan["top_n"] == 1
    assert plan["rank_order"] == "desc"
    assert plan["product_grain"] == product_keys
    assert plan["analysis_output_columns"] == output_columns
    assert step["metric"] == "WIP"
    assert step["top_n"] == 1
    assert step["rank_order"] == "desc"
    assert step["group_by"] == product_keys
    assert step["output_columns"] == output_columns
    assert _filter_values(payload["retrieval_jobs"][0], "OPER_NAME") == ["D/A1", "D/A2", "D/A3", "D/A4", "D/A5", "D/A6"]
    assert any("retrieval_jobs가 없어" in item for item in payload["info"])
    assert any("step_plan이 없어" in item for item in payload["info"])
    assert not any("retrieval_jobs가 없어" in item for item in payload["warnings"])


def test_intent_normalizer_augments_existing_jobs_from_metadata(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 DA공정에서 재공, 생산량과 목표값 그리고 생산달성율을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "production_wip_target_rate",
        "datasets": ["production_today", "wip_today", "target"],
        "retrieval_jobs": [
            {"dataset_key": "production_today", "source_alias": "prod", "filters": [], "params": {}, "source_config": {}},
            {"dataset_key": "wip_today", "source_alias": "wip", "filters": [], "params": {}},
            {"dataset_key": "target", "source_alias": "target", "filters": [], "params": {}},
        ],
        "step_plan": [{"step_id": "join", "operation": "join"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    jobs = {job["dataset_key"]: job for job in payload["retrieval_jobs"]}

    assert jobs["production_today"]["params"]["DATE"] == "20260612"
    assert jobs["wip_today"]["params"]["DATE"] == "20260612"
    assert jobs["production_today"]["source_config"]["db_key"] == "PNT_RPT"
    assert "query_template" in jobs["production_today"]["source_config"]
    assert jobs["target"]["source_config"]["doc_id"] == "GOODOCS_TARGET2_DOCUMENT_ID"
    assert jobs["target"]["date_format"] == "YYYY-MM-DD"
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
    assert any("params/filters를 보완" in item for item in payload["info"])
    assert not any("params/filters를 보완" in item for item in payload["warnings"])


def test_intent_normalizer_uses_product_terms_for_existing_jobs(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

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
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

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
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

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


def test_intent_normalizer_uses_state_product_key_summary_without_full_rows(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("그 제품이 물려 있는 설비를 보여줘", "test-session")
    payload["state"] = {
        "current_data": {
            "columns": ["MODE", "WIP"],
            "rows": [{"MODE": "LPDDR5", "WIP": 10}],
            "row_count": 200,
            "data_is_preview": True,
            "product_key_columns": ["MODE"],
            "product_key_values": [{"MODE": "LPDDR5"}, {"MODE": "HBM"}],
            "product_key_count": 2,
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
    assert plan["state_product_keys"] == [{"MODE": "LPDDR5"}, {"MODE": "HBM"}]
    assert any(item.get("field") == "PRODUCT_GRAIN" for item in payload["retrieval_jobs"][0]["filters"])


def test_intent_normalizer_prunes_lot_status_for_followup_equipment_count(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("이 제품의 이 공정에 할당된 장비 대수를 알려줘", "test-session")
    payload["state"] = {
        "current_data": {
            "columns": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "WIP"],
            "rows": [{"TECH": "FC", "DEN": "128G", "MODE": "LPDDR5", "PKG_TYPE1": "UFBGA", "PKG_TYPE2": "MOBILE", "LEAD": "LF", "MCP_NO": "EMPTY", "WIP": 10}],
            "product_key_columns": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"],
            "product_key_values": [{"TECH": "FC", "DEN": "128G", "MODE": "LPDDR5", "PKG_TYPE1": "UFBGA", "PKG_TYPE2": "MOBILE", "LEAD": "LF", "MCP_NO": "EMPTY"}],
            "product_key_count": 1,
            "data_ref": {"store": "mongodb", "ref_id": "previous-result", "collection_name": "agent_v2_result_store"},
        }
    }
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "followup_transform",
        "analysis_kind": "equipment_by_model",
        "datasets": ["equipment_status", "lot_status"],
        "retrieval_jobs": [
            {"dataset_key": "equipment_status", "source_alias": "equipment", "filters": [], "params": {}},
            {"dataset_key": "lot_status", "source_alias": "lot_status", "filters": [{"field": "OPER_NAME", "op": "in", "values": ["D/A1"]}], "params": {}},
        ],
        "step_plan": [{"step_id": "equipment_count", "operation": "count", "source_alias": "equipment"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]

    assert plan["analysis_kind"] == "equipment_count_for_previous_products"
    assert plan["datasets"] == ["equipment_status"]
    assert [job["dataset_key"] for job in payload["retrieval_jobs"]] == ["equipment_status"]
    assert payload["retrieval_jobs"][0]["filters"] == [{"field": "PRODUCT_GRAIN", "op": "from_state"}]
    assert plan["step_plan"][0]["operation"] == "equipment_count_for_previous_products"
    assert plan["state_hydrate_mode"] == "summary"


def test_retrieval_adapter_adds_standard_columns_from_physical_catalog_aliases(monkeypatch: Any) -> None:
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    retrieval_adapter = load_component("langflow_components/main_flow/05_retrieval_payload_adapter.py")

    payload = load_seed_metadata_payload(metadata_loader, {"state": {}}, monkeypatch)
    retrieval_payload = {
        "source_results": [
            {
                "dataset_key": "equipment_status",
                "source_alias": "equipment",
                "source_type": "oracle",
                "data": [{"EQPID": "EQP1", "PKG1": "UFBGA", "PKG2": "MOBILE", "MCPSALENO": "EMPTY", "MODE": "LPDDR5"}],
            }
        ]
    }

    adapted = retrieval_adapter.adapt_retrieval_payload(payload, retrieval_payload)
    row = adapted["runtime_sources"]["equipment"][0]

    assert row["PKG_TYPE1"] == "UFBGA"
    assert row["PKG_TYPE2"] == "MOBILE"
    assert row["MCP_NO"] == "EMPTY"


def test_intent_normalizer_marks_full_state_hydrate_for_previous_result_row_analysis(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("이전 결과 전체 데이터를 다시 보여줘", "test-session")
    payload["state"] = {
        "current_data": {
            "columns": ["MODE", "WIP"],
            "rows": [{"MODE": "LPDDR5", "WIP": 10}],
            "row_count": 200,
            "data_ref": {"store": "mongodb", "ref_id": "previous-result", "collection_name": "agent_v2_result_store"},
            "data_is_preview": True,
        }
    }
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "followup_transform",
        "analysis_kind": "detail_rows",
        "datasets": [],
        "retrieval_jobs": [],
        "depends_on_state": True,
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]

    assert plan["requires_full_state_hydrate"] is True
    assert plan["state_hydrate_mode"] == "full"
    assert plan["state_hydrate_reason"] == "followup_analysis_needs_previous_rows"
    assert any("MongoDB에서 전체 row를 복원" in item for item in payload["info"])


def test_intent_normalizer_maps_logical_required_columns_to_dataset_columns(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

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


def test_intent_normalizer_repairs_lot_count_kind_from_generic_aggregate(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("현재 작업대기 Lot 수량을 공정별로 알려줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "aggregate_wip_total",
        "datasets": ["lot_status"],
        "filters": [{"field": "LOT_STAT_CD", "op": "in", "values": ["WAITING"]}],
        "metric": "LOT_ID",
        "analysis_output_columns": ["OPER_NAME", "LOT_COUNT"],
        "retrieval_jobs": [
            {
                "dataset_key": "lot_status",
                "source_alias": "lot_data",
                "filters": [{"field": "LOT_STAT_CD", "op": "in", "values": ["WAITING"]}],
                "required_columns": ["OPER_NAME", "LOT_ID"],
            }
        ],
        "step_plan": [
            {
                "step_id": "aggregate_waiting_lots",
                "operation": "aggregate",
                "source_alias": "lot_data",
                "metric": "LOT_ID",
                "aggregation": "nunique",
                "group_by": ["OPER_NAME"],
                "output_columns": ["OPER_NAME", "LOT_COUNT"],
            }
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["intent_plan"]["analysis_kind"] == "lot_count_by_process"
    assert payload["intent_plan"]["step_plan"][0]["operation"] == "lot_count_by_process"
    assert payload["intent_plan"]["step_plan"][0]["group_by_columns"] == ["OPER_SHORT_DESC"]
    assert payload["retrieval_jobs"][0]["dataset_key"] == "lot_status"
    assert "OPER_SHORT_DESC" in payload["retrieval_jobs"][0]["required_columns"]
    assert any("LOT_ID unique count" in item for item in payload["info"])


def test_intent_normalizer_adds_primary_quantity_to_equipment_columns(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/02_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/04_intent_plan_normalizer.py")

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
    pandas_executor = load_component("langflow_components/main_flow/07_pandas_code_executor.py")
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


def test_pandas_executor_rewrites_pd_inf_for_pandas_compatibility() -> None:
    pandas_executor = load_component("langflow_components/main_flow/07_pandas_code_executor.py")
    payload = {
        "intent_plan": {"analysis_kind": "production_wip_target_rate", "product_grain": []},
        "state": {},
        "runtime_sources": {},
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "result_df = pd.DataFrame([{'WIP': 5, 'PRODUCTION': 10, 'OUT_PLAN': 0}])",
                "result_df['ACHIEVEMENT_RATE'] = result_df['PRODUCTION'].div(result_df['OUT_PLAN']).replace([pd.inf, -pd.inf], 0).fillna(0)",
            ]
        ),
        "output_columns": ["WIP", "PRODUCTION", "OUT_PLAN", "ACHIEVEMENT_RATE"],
        "reasoning_steps": ["Handle division by zero."],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["rows"][0]["ACHIEVEMENT_RATE"] == 0
    assert "pd.inf" not in result["analysis"]["analysis_code"]


def test_pandas_executor_normalizes_common_result_aliases() -> None:
    pandas_executor = load_component("langflow_components/main_flow/07_pandas_code_executor.py")
    join_payload = {
        "intent_plan": {"analysis_kind": "aggregate_join", "product_grain": ["MODE"]},
        "state": {},
        "runtime_sources": {},
    }
    join_llm_json = {
        "code": "result_df = pd.DataFrame([{'MODE': 'LPDDR5', 'PRODUCTION_QUANTITY': 10, 'WIP_QUANTITY': 4}])",
        "output_columns": ["MODE", "PRODUCTION_QUANTITY", "WIP_QUANTITY"],
        "reasoning_steps": [],
    }

    join_result = pandas_executor.execute_pandas_from_llm(join_payload, json.dumps(join_llm_json, ensure_ascii=False))

    assert join_result["analysis"]["columns"] == ["MODE", "PRODUCTION", "WIP"]
    assert join_result["analysis"]["rows"][0]["PRODUCTION"] == 10
    assert join_result["analysis"]["rows"][0]["WIP"] == 4

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

    equipment_payload = {
        "intent_plan": {"analysis_kind": "equipment_by_model"},
        "state": {},
        "runtime_sources": {},
    }
    equipment_llm_json = {
        "code": "result_df = pd.DataFrame([{'EQP_MODEL': 'MODEL-A', 'EQP_COUNT': 2, 'TOTAL_PRESS_CNT': 9}])",
        "output_columns": ["EQP_MODEL", "EQP_COUNT", "TOTAL_PRESS_CNT"],
        "reasoning_steps": [],
    }

    equipment_result = pandas_executor.execute_pandas_from_llm(
        equipment_payload, json.dumps(equipment_llm_json, ensure_ascii=False)
    )

    assert equipment_result["analysis"]["columns"] == ["EQP_MODEL", "EQP_COUNT", "PRESS_CNT"]
    assert equipment_result["analysis"]["rows"][0]["PRESS_CNT"] == 9


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
