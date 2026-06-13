from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_component(path: str):
    component_path = ROOT / path
    spec = importlib.util.spec_from_file_location(component_path.stem, component_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_langflow_llm_node_style_flow_contract() -> None:
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
    payload = metadata_loader.load_metadata_payload(
        payload,
        metadata_source="local",
        metadata_dir=str(ROOT / "metadata"),
    )

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


def test_intent_normalizer_builds_fallback_jobs_when_llm_omits_jobs() -> None:
    request_loader = load_component("langflow_components/main_flow/00_request_state_loader.py")
    metadata_loader = load_component("langflow_components/main_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/main_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 DA공정에서 재공, 생산량과 목표값 그리고 생산달성율을 보여줘", "test-session")
    payload = metadata_loader.load_metadata_payload(
        payload,
        metadata_source="local",
        metadata_dir=str(ROOT / "metadata"),
    )
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
        "scope_production_today",
        "scope_wip_today",
        "scope_target",
    ]
    assert [job["source_type"] for job in payload["retrieval_jobs"]] == ["oracle", "oracle", "goodocs"]
    assert payload["intent_plan"]["step_plan"]
    assert any("fallback jobs" in item for item in payload["warnings"])


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
