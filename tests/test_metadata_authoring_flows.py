from __future__ import annotations

import importlib.util
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_module(relative_path: str):
    path = PROJECT_ROOT / relative_path
    module_name = "authoring_test_" + path.stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_domain_authoring_normalizes_lot_count_and_blocks_pending_duplicate() -> None:
    normalizer = load_module("langflow_components/domain_authoring_flow/04_domain_authoring_result_normalizer.py")
    similarity = load_module("langflow_components/domain_authoring_flow/05_domain_similarity_checker.py")
    writer = load_module("langflow_components/domain_authoring_flow/07_domain_review_writer.py")
    response = load_module("langflow_components/domain_authoring_flow/08_domain_authoring_response_builder.py")

    payload = {
        "metadata_type": "domain",
        "existing_items": [{"section": "quantity_terms", "key": "lot_count", "aliases": ["Lot 수량"]}],
        "duplicate_decision": {"action": "ask"},
        "errors": [],
        "warnings": [],
    }
    llm_json = {
        "items": [
            {
                "section": "quantity_terms",
                "key": "lot_count",
                "payload": {
                    "aliases": ["Lot 수량"],
                    "dataset_key": "lot_status",
                    "quantity_column": "LOT_ID",
                    "aggregation": "count_distinct",
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }
    normalized = normalizer.normalize_domain_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))
    assert normalized["items"][0]["payload"]["aggregation"] == "nunique"

    checked = similarity.check_domain_similarity(normalized, "ask")
    assert checked["existing_matches"]
    assert checked["duplicate_decision"]["requires_user_choice"] is True

    written = writer.review_and_write_domain_payload(checked, '{"ready_to_save": true, "supplement_requests": []}')
    assert written["write_result"]["status"] == "skipped"
    assert "선택" in written["write_result"]["skipped_reason"]

    api_response = response.build_domain_authoring_response(written)
    assert "비슷한 기존 정보" in api_response["message"]


def test_domain_authoring_preserves_dataset_specific_conditions_and_metric_dependencies() -> None:
    normalizer = load_module("langflow_components/domain_authoring_flow/04_domain_authoring_result_normalizer.py")
    payload = {"metadata_type": "domain", "errors": [], "warnings": []}
    llm_json = {
        "items": [
            {
                "section": "product_terms",
                "key": "hbm",
                "payload": {
                    "aliases": ["HBM"],
                    "condition": {"TSV_DIE_TYP": {"exists": True}},
                    "condition_by_family": {"equipment": {"PKG_TYPE1": "HBM"}},
                },
            },
            {
                "section": "metric_terms",
                "key": "achievement_rate",
                "payload": {
                    "aliases": ["달성율"],
                    "formula": "sum(PRODUCTION) / sum(OUT_PLAN) * 100",
                    "calculation_rule": "aggregate_first",
                    "required_quantity_terms": ["production", "target"],
                    "output_column": "ACHIEVEMENT_RATE",
                },
            },
            {
                "section": "analysis_recipes",
                "key": "production_wip_target_rate",
                "payload": {
                    "aliases": ["생산달성율"],
                    "intent_type": "multi_source_analysis",
                    "default_analysis_kind": "production_wip_target_rate",
                    "required_quantity_terms": ["production", "wip", "target"],
                    "required_dataset_families": ["production", "wip", "target"],
                    "metric_terms": ["achievement_rate"],
                    "grain_policy": "question_or_product_grain",
                    "source_aliases_by_family": {"production": "production_data"},
                    "output_columns": ["WIP", "PRODUCTION", "OUT_PLAN", "ACHIEVEMENT_RATE"],
                },
            },
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_domain_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))
    items = {item["key"]: item for item in normalized["items"]}

    assert normalized["errors"] == []
    assert items["hbm"]["payload"]["condition_by_family"] == {"equipment": {"PKG_TYPE1": "HBM"}}
    assert items["achievement_rate"]["payload"]["required_quantity_terms"] == ["production", "target"]
    assert items["achievement_rate"]["payload"]["output_column"] == "ACHIEVEMENT_RATE"
    assert items["production_wip_target_rate"]["section"] == "analysis_recipes"
    assert items["production_wip_target_rate"]["payload"]["required_dataset_families"] == ["production", "wip", "target"]
    assert items["production_wip_target_rate"]["payload"]["output_columns"] == [
        "WIP",
        "PRODUCTION",
        "OUT_PLAN",
        "ACHIEVEMENT_RATE",
    ]


def test_table_catalog_authoring_requires_source_config_and_detects_same_dataset_key() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    similarity = load_module("langflow_components/table_catalog_authoring_flow/05_table_catalog_similarity_checker.py")

    payload = {
        "metadata_type": "table_catalog",
        "existing_items": [{"dataset_key": "wip_today", "dataset_family": "wip", "date_scope": "current_day", "source_type": "oracle"}],
        "duplicate_decision": {"action": "ask"},
        "errors": [],
        "warnings": [],
    }
    llm_json = {
        "items": [
            {
                "dataset_key": "wip_today",
                "payload": {
                    "display_name": "WIP Today",
                    "dataset_family": "wip",
                    "date_scope": "current_day",
                    "source_type": "oracle",
                    "source_config": {
                        "source_type": "oracle",
                        "db_key": "PNT_RPT",
                        "query_template": "SELECT WORK_DT, WIP FROM PKG_WIP_TODAY WHERE WORK_DT = {DATE}",
                    },
                    "columns": ["WORK_DT", "WIP"],
                    "filter_mappings": {"DATE": ["WORK_DT"]},
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }
    normalized = normalizer.normalize_table_catalog_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))
    assert normalized["errors"] == []
    assert normalized["items"][0]["dataset_key"] == "wip_today"

    checked = similarity.check_table_catalog_similarity(normalized, "ask")
    assert checked["existing_matches"][0]["match_type"] == "same_dataset_key"
    assert checked["duplicate_decision"]["requires_user_choice"] is True


def test_table_catalog_authoring_normalizes_detail_columns_and_filter_mappings() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    payload = {"metadata_type": "table_catalog", "errors": [], "warnings": []}
    llm_json = {
        "items": [
            {
                "dataset_key": "target",
                "payload": {
                    "display_name": "Production Plan",
                    "dataset_family": "target",
                    "source_type": "goodocs",
                    "source_config": {
                        "source_type": "goodocs",
                        "doc_id": "TARGET_DOC",
                        "sheet_name": "daily_target",
                    },
                    "date_format": "YYYY-MM-DD",
                    "columns": ["DATE", "MODE", "OUT_PLAN"],
                    "filter_mappings": {"DATE": "DATE", "MODE": ["MODE"]},
                    "default_detail_columns": "DATE",
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_table_catalog_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))

    assert normalized["errors"] == []
    item_payload = normalized["items"][0]["payload"]
    assert item_payload["filter_mappings"] == {"DATE": ["DATE"], "MODE": ["MODE"]}
    assert item_payload["default_detail_columns"] == ["DATE"]
    assert item_payload["date_format"] == "YYYY-MM-DD"


def test_main_flow_filter_authoring_detects_alias_overlap() -> None:
    normalizer = load_module("langflow_components/main_flow_filters_authoring_flow/04_main_flow_filter_authoring_result_normalizer.py")
    similarity = load_module("langflow_components/main_flow_filters_authoring_flow/05_main_flow_filter_similarity_checker.py")

    payload = {
        "metadata_type": "main_flow_filter",
        "existing_items": [
            {
                "filter_key": "DATE",
                "aliases": ["오늘", "금일"],
                "column_candidates": ["WORK_DT"],
                "semantic_role": "date",
            }
        ],
        "duplicate_decision": {"action": "ask"},
        "errors": [],
        "warnings": [],
    }
    llm_json = {
        "items": [
            {
                "filter_key": "WORK_DATE",
                "payload": {
                    "display_name": "작업일",
                    "aliases": ["오늘", "작업일"],
                    "column_candidates": ["WORK_DT", "BASE_DT"],
                    "semantic_role": "date",
                    "value_type": "date",
                    "operator": "eq",
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }
    normalized = normalizer.normalize_main_flow_filter_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))
    assert normalized["errors"] == []
    checked = similarity.check_main_flow_filter_similarity(normalized, "ask")
    assert checked["existing_matches"] == []
    assert checked["conflict_warnings"]
    assert checked["conflict_warnings"][0]["warning_type"] == "alias_overlap"


def test_main_flow_filter_authoring_normalizes_runtime_hint_lists() -> None:
    normalizer = load_module("langflow_components/main_flow_filters_authoring_flow/04_main_flow_filter_authoring_result_normalizer.py")
    payload = {"metadata_type": "main_flow_filter", "errors": [], "warnings": []}
    llm_json = {
        "items": [
            {
                "filter_key": "DATE",
                "payload": {
                    "display_name": "기준일",
                    "aliases": "오늘",
                    "column_candidates": "WORK_DT",
                    "semantic_role": "date",
                    "value_type": "date",
                    "sample_values": "20260612",
                    "required_params": "DATE",
                    "value_mappings": [],
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_main_flow_filter_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))
    item_payload = normalized["items"][0]["payload"]

    assert normalized["errors"] == []
    assert item_payload["aliases"] == ["오늘"]
    assert item_payload["column_candidates"] == ["WORK_DT"]
    assert item_payload["sample_values"] == ["20260612"]
    assert item_payload["required_params"] == ["DATE"]
    assert item_payload["value_mappings"] == {}
