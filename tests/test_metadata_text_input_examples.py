from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


DOMAIN_BULK_TEXT = """업무 용어를 등록할게요.
DA는 D/A라고도 부르고 실제 공정은 D/A1, D/A2, D/A3, D/A4, D/A5, D/A6입니다.
WB는 W/B라고도 부르고 실제 공정은 W/B1, W/B2, W/B3, W/B4, W/B5, W/B6입니다.
DP는 D/P라고도 부르고 실제 공정은 D/P1, D/P2입니다.
BG는 B/G라고도 부르고 실제 공정은 B/G1, B/G2입니다.
WSD는 WSD라고 부르고 실제 공정은 WSD1, WSD2입니다.
DS는 D/S라고도 부르고 실제 공정은 D/S1, D/S2입니다.
FCB는 FCB라고 부르고 실제 공정은 FCB1, FCB2입니다.
FCBH는 FCBH라고 부르고 실제 공정은 FCBH1, FCBH2입니다.
BM은 B/M 또는 비엠이라고도 부르고 실제 공정은 B/M1, B/M2입니다.
HBM, 3DS, TSV는 TSV_DIE_TYP 값이 있고 비어 있지 않은 제품입니다. equipment 계열 데이터에서는 PKG_TYPE1이 HBM인 제품으로 보면 됩니다.
LPDDR5는 MODE 값이 LPDDR5인 제품입니다.
AUTO향은 MCP_NO 값이 있고 마지막 문자가 I, O, N, P, Q, V 중 하나인 제품입니다.
생산량은 production 계열의 PRODUCTION 합계이고, 재공은 wip 계열의 WIP 합계입니다.
Wafer 수량은 lot_status의 WF_QTY 합계이고, Die 수량은 lot_status의 SUB_PROD_QTY 합계입니다.
Lot 수량은 lot_status에서 LOT_ID를 중복 없이 세고 LOT_COUNT로 보여 주세요.
생산달성률은 생산량 합계 / OUT 계획 합계 * 100이고 생산량과 목표값이 필요하며 결과 컬럼명은 ACHIEVEMENT_RATE입니다.
목표 미달은 OUT 계획 합계 - 생산량 합계이며 음수면 0이고 생산량과 목표값이 필요하며 결과 컬럼명은 BALANCE입니다.
동적TAT는 재공 합계 / 생산량 합계이고 재공과 생산량이 필요하며 결과 컬럼명은 DYNAMIC_TAT입니다.
Hold Lot은 LOT_HOLD_STAT_CD가 HOLD 또는 OnHold인 row 목록입니다.
작업대기 Lot은 LOT_STAT_CD가 WAITING인 LOT_ID 중복 없는 수량입니다.
작업중 Lot은 LOT_STAT_CD가 RUNNING인 LOT_ID 중복 없는 수량입니다.
생산달성율 질문은 생산량, 재공, 목표 데이터가 필요하고 분석 방식은 production_wip_target_rate입니다. 묶는 기준은 질문에서 전체라고 하면 전체 합계, 제품별이라고 하면 제품 기준으로 보면 됩니다.
생산 저조 질문은 생산량과 목표 데이터가 필요하고 분석 방식은 low_output_vs_target입니다. 묶는 기준은 질문에서 말한 기준을 따릅니다.
Lot, Wafer, Die 수량 요약 질문은 lot_status 데이터를 사용하고 분석 방식은 lot_quantity_summary입니다.
제품 식별 컬럼은 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO입니다."""


TABLE_BULK_TEXT = """데이터셋 정보를 등록할게요.
production_today, production, wip_today, wip, target, lot_status, hold_history, equipment_status, capacity를 등록합니다.
각 데이터셋의 source, 조회문, 필수 입력값, 필터 매핑, 컬럼은 시스템 담당자에게 받은 값 그대로 사용합니다."""


FILTER_BULK_TEXT = """질문에서 뽑아야 하는 필터 정보를 등록할게요.
DATE, OPER_NAME, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, DEVICE_DESC, TSV_DIE_TYP, OPER_NUM,
LOT_ID, LOT_STAT_CD, LOT_HOLD_STAT_CD, EQP_ID, EQP_MODEL, RECIPE_ID를 등록합니다.
각 필터에는 작업자가 말하는 표현, 실제 후보 컬럼, 필터 역할을 함께 적습니다."""


def load_module(relative_path: str):
    path = PROJECT_ROOT / relative_path
    module_name = "metadata_text_input_test_" + path.stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FakeReplaceResult:
    def __init__(self, upserted_id: str | None, modified_count: int) -> None:
        self.upserted_id = upserted_id
        self.modified_count = modified_count


class FakeCollection:
    def __init__(self, docs: dict[str, dict[str, Any]]) -> None:
        self.docs = docs

    def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        for doc in self.docs.values():
            if all(doc.get(key) == value for key, value in query.items()):
                return doc
        return None

    def replace_one(self, query: dict[str, Any], doc: dict[str, Any], upsert: bool = False) -> FakeReplaceResult:
        key = str(query.get("_id") or doc["_id"])
        existed = key in self.docs
        self.docs[key] = dict(doc)
        return FakeReplaceResult(None if existed else key, 1 if existed else 0)


class FakeDatabase:
    def __init__(self, db_name: str, store: dict[tuple[str, str], dict[str, dict[str, Any]]]) -> None:
        self.db_name = db_name
        self.store = store

    def __getitem__(self, collection_name: str) -> FakeCollection:
        docs = self.store.setdefault((self.db_name, collection_name), {})
        return FakeCollection(docs)


class FakeMongoClient:
    store: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}

    def __init__(self, mongo_uri: str, **_: Any) -> None:
        self.mongo_uri = mongo_uri

    def __getitem__(self, db_name: str) -> FakeDatabase:
        return FakeDatabase(db_name, self.store)

    def close(self) -> None:
        return None


def install_fake_mongo(monkeypatch: Any, writer_module: Any) -> dict[tuple[str, str], dict[str, dict[str, Any]]]:
    FakeMongoClient.store = {}
    fake_pymongo = SimpleNamespace(MongoClient=FakeMongoClient)
    monkeypatch.setattr(writer_module, "import_module", lambda name: fake_pymongo)
    return FakeMongoClient.store


def read_json(relative_path: str) -> Any:
    return json.loads((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))


def domain_items_from_current_metadata() -> list[dict[str, Any]]:
    data = read_json("metadata/domain_items.json")
    items: list[dict[str, Any]] = []
    for section in ["process_groups", "product_terms", "quantity_terms", "metric_terms", "analysis_recipes", "status_terms"]:
        for key, payload in data[section].items():
            items.append({"section": section, "key": key, "payload": payload, "confidence": "high"})
    items.append(
        {
            "section": "product_key_columns",
            "key": "product_key_columns",
            "columns": data["product_key_columns"],
            "payload": {"columns": data["product_key_columns"]},
            "confidence": "high",
        }
    )
    return items


def table_items_from_current_metadata() -> list[dict[str, Any]]:
    data = read_json("metadata/table_catalog.json")
    return [
        {"dataset_key": dataset_key, "payload": payload, "confidence": "high"}
        for dataset_key, payload in data["datasets"].items()
    ]


FILTER_AUTHORING_HINTS: dict[str, dict[str, Any]] = {
    "DATE": {"aliases": ["기준일", "일자", "날짜", "오늘", "어제", "작업일"], "semantic_role": "date", "value_type": "date"},
    "OPER_NAME": {"aliases": ["공정명", "공정", "오퍼명"], "semantic_role": "process"},
    "TECH": {"aliases": ["제품 기술", "TECH"], "semantic_role": "product_attribute"},
    "DEN": {"aliases": ["제품 용량", "DEN"], "semantic_role": "product_attribute"},
    "MODE": {"aliases": ["제품 모드", "MODE"], "semantic_role": "product_attribute"},
    "PKG_TYPE1": {"aliases": ["패키지 타입1", "PKG_TYPE1"], "semantic_role": "package_attribute"},
    "PKG_TYPE2": {"aliases": ["패키지 타입2", "PKG_TYPE2"], "semantic_role": "package_attribute"},
    "LEAD": {"aliases": ["Lead", "LEAD"], "semantic_role": "product_attribute"},
    "MCP_NO": {"aliases": ["제품 코드", "MCP 번호", "MCP NO"], "semantic_role": "product_code"},
    "DEVICE_DESC": {"aliases": ["device", "device code", "DEVICE_DESC"], "semantic_role": "device"},
    "TSV_DIE_TYP": {"aliases": ["HBM 판별", "3DS 판별", "TSV 판별"], "semantic_role": "product_condition"},
    "OPER_NUM": {"aliases": ["공정 번호", "OPER_NUM"], "semantic_role": "process_number"},
    "LOT_ID": {"aliases": ["Lot ID", "LOT 번호"], "semantic_role": "lot_id"},
    "LOT_STAT_CD": {"aliases": ["Lot 작업 상태", "LOT 상태"], "semantic_role": "lot_status"},
    "LOT_HOLD_STAT_CD": {"aliases": ["Lot hold 상태", "Hold 상태"], "semantic_role": "hold_status"},
    "EQP_ID": {"aliases": ["장비 ID", "장비 번호"], "semantic_role": "equipment_id"},
    "EQP_MODEL": {"aliases": ["장비 모델", "EQP_MODEL"], "semantic_role": "equipment_model"},
    "RECIPE_ID": {"aliases": ["Recipe ID", "레시피"], "semantic_role": "recipe_id"},
}


def filter_items_from_current_metadata() -> list[dict[str, Any]]:
    data = read_json("metadata/main_flow_filters.json")
    items = []
    for filter_key, payload in data.items():
        hints = FILTER_AUTHORING_HINTS[filter_key]
        authoring_payload = {
            "display_name": payload.get("description", filter_key),
            "description": payload.get("description", ""),
            "aliases": hints["aliases"],
            "column_candidates": payload["column_candidates"],
            "semantic_role": hints["semantic_role"],
            "value_type": hints.get("value_type", "string"),
            "value_shape": "scalar",
            "operator": "eq",
        }
        items.append({"filter_key": filter_key, "payload": authoring_payload, "confidence": "high"})
    return items


def run_domain_authoring_flow(raw_text: str, items: list[dict[str, Any]], monkeypatch: Any) -> tuple[dict[str, Any], dict[Any, Any]]:
    request = load_module("langflow_components/domain_authoring_flow/00_domain_authoring_request_loader.py")
    refine = load_module("langflow_components/domain_authoring_flow/02_domain_text_refinement_normalizer.py")
    normalizer = load_module("langflow_components/domain_authoring_flow/04_domain_authoring_result_normalizer.py")
    similarity = load_module("langflow_components/domain_authoring_flow/05_domain_similarity_checker.py")
    writer = load_module("langflow_components/domain_authoring_flow/07_domain_review_writer.py")
    store = install_fake_mongo(monkeypatch, writer)

    payload = request.build_domain_authoring_request(
        raw_text,
        mongo_uri="mongodb://fake",
        duplicate_action="merge",
        load_existing="false",
    )
    refined = refine.normalize_domain_refinement(payload, json.dumps({"refined_text": raw_text, "needs_more_input": False}, ensure_ascii=False))
    normalized = normalizer.normalize_domain_authoring_result(
        refined,
        json.dumps({"items": items, "missing_information": [], "warnings": []}, ensure_ascii=False),
    )
    assert normalized["errors"] == []
    checked = similarity.check_domain_similarity(normalized, "merge")
    written = writer.review_and_write_domain_payload(
        checked,
        json.dumps({"ready_to_save": True, "supplement_requests": []}, ensure_ascii=False),
        mongo_uri="mongodb://fake",
        duplicate_action="merge",
    )
    return written, store


def run_table_authoring_flow(raw_text: str, items: list[dict[str, Any]], monkeypatch: Any) -> tuple[dict[str, Any], dict[Any, Any]]:
    request = load_module("langflow_components/table_catalog_authoring_flow/00_table_catalog_authoring_request_loader.py")
    refine = load_module("langflow_components/table_catalog_authoring_flow/02_table_catalog_text_refinement_normalizer.py")
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    similarity = load_module("langflow_components/table_catalog_authoring_flow/05_table_catalog_similarity_checker.py")
    writer = load_module("langflow_components/table_catalog_authoring_flow/07_table_catalog_review_writer.py")
    store = install_fake_mongo(monkeypatch, writer)

    payload = request.build_table_catalog_authoring_request(
        raw_text,
        mongo_uri="mongodb://fake",
        duplicate_action="merge",
        load_existing="false",
    )
    refined = refine.normalize_table_catalog_refinement(payload, json.dumps({"refined_text": raw_text, "needs_more_input": False}, ensure_ascii=False))
    normalized = normalizer.normalize_table_catalog_authoring_result(
        refined,
        json.dumps({"items": items, "missing_information": [], "warnings": []}, ensure_ascii=False),
    )
    assert normalized["errors"] == []
    checked = similarity.check_table_catalog_similarity(normalized, "merge")
    written = writer.review_and_write_table_catalog_payload(
        checked,
        json.dumps({"ready_to_save": True, "supplement_requests": []}, ensure_ascii=False),
        mongo_uri="mongodb://fake",
        duplicate_action="merge",
    )
    return written, store


def run_filter_authoring_flow(raw_text: str, items: list[dict[str, Any]], monkeypatch: Any) -> tuple[dict[str, Any], dict[Any, Any]]:
    request = load_module("langflow_components/main_flow_filters_authoring_flow/00_main_flow_filter_authoring_request_loader.py")
    refine = load_module("langflow_components/main_flow_filters_authoring_flow/02_main_flow_filter_text_refinement_normalizer.py")
    normalizer = load_module("langflow_components/main_flow_filters_authoring_flow/04_main_flow_filter_authoring_result_normalizer.py")
    similarity = load_module("langflow_components/main_flow_filters_authoring_flow/05_main_flow_filter_similarity_checker.py")
    writer = load_module("langflow_components/main_flow_filters_authoring_flow/07_main_flow_filter_review_writer.py")
    store = install_fake_mongo(monkeypatch, writer)

    payload = request.build_main_flow_filter_authoring_request(
        raw_text,
        mongo_uri="mongodb://fake",
        duplicate_action="merge",
        load_existing="false",
    )
    refined = refine.normalize_main_flow_filter_refinement(payload, json.dumps({"refined_text": raw_text, "needs_more_input": False}, ensure_ascii=False))
    normalized = normalizer.normalize_main_flow_filter_authoring_result(
        refined,
        json.dumps({"items": items, "missing_information": [], "warnings": []}, ensure_ascii=False),
    )
    assert normalized["errors"] == []
    checked = similarity.check_main_flow_filter_similarity(normalized, "merge")
    written = writer.review_and_write_main_flow_filter_payload(
        checked,
        json.dumps({"ready_to_save": True, "supplement_requests": []}, ensure_ascii=False),
        mongo_uri="mongodb://fake",
        duplicate_action="merge",
    )
    return written, store


def test_worker_bulk_domain_text_input_saves_all_current_domain_metadata(monkeypatch: Any) -> None:
    items = domain_items_from_current_metadata()
    written, store = run_domain_authoring_flow(DOMAIN_BULK_TEXT, items, monkeypatch)

    assert written["raw_text"] == DOMAIN_BULK_TEXT
    assert written["write_result"]["status"] == "ok"
    assert written["write_result"]["saved_count"] == 30
    docs = store[("metadata_driven_agent_v2", "agent_v2_domain_items")]
    assert set(docs) >= {
        "domain:process_groups:DA",
        "domain:product_terms:hbm",
        "domain:product_terms:lpddr5",
        "domain:quantity_terms:lot_count",
        "domain:quantity_terms:wafer_qty",
        "domain:quantity_terms:die_qty",
        "domain:analysis_recipes:production_wip_target_rate",
        "domain:analysis_recipes:lot_quantity_summary",
    }
    assert docs["domain:product_terms:hbm"]["payload"]["condition_by_family"]["equipment"] == {"PKG_TYPE1": "HBM"}
    assert docs["domain:quantity_terms:lot_count"]["payload"]["aggregation"] == "nunique"
    assert docs["domain:metric_terms:achievement_rate"]["payload"]["required_quantity_terms"] == ["production", "target"]
    assert docs["domain:analysis_recipes:production_wip_target_rate"]["payload"]["grain_policy"] == "question_or_product_grain"
    assert docs["domain:analysis_recipes:production_wip_target_rate"]["payload"]["source_aliases_by_family"] == {
        "production": "production_data",
        "wip": "wip_data",
        "target": "target_data",
    }
    assert docs["domain:analysis_recipes:lot_quantity_summary"]["payload"]["output_columns"] == [
        "LOT_COUNT",
        "WF_QTY",
        "DIE_QTY",
    ]
    assert docs["domain:status_terms:hold_lot"]["payload"]["result_mode"] == "detail_rows"


def test_worker_single_domain_text_input_saves_one_process_group(monkeypatch: Any) -> None:
    data = read_json("metadata/domain_items.json")
    item = {"section": "process_groups", "key": "DA", "payload": data["process_groups"]["DA"], "confidence": "high"}
    written, store = run_domain_authoring_flow(
        "DA 공정 그룹을 등록할게요. DA는 D/A라고도 부르고 실제 공정은 D/A1부터 D/A6까지입니다.",
        [item],
        monkeypatch,
    )

    assert written["write_result"]["status"] == "ok"
    assert written["write_result"]["saved_count"] == 1
    docs = store[("metadata_driven_agent_v2", "agent_v2_domain_items")]
    assert docs["domain:process_groups:DA"]["payload"]["processes"] == ["D/A1", "D/A2", "D/A3", "D/A4", "D/A5", "D/A6"]


def test_worker_bulk_table_text_input_saves_all_current_datasets(monkeypatch: Any) -> None:
    items = table_items_from_current_metadata()
    written, store = run_table_authoring_flow(TABLE_BULK_TEXT, items, monkeypatch)

    assert written["raw_text"] == TABLE_BULK_TEXT
    assert written["write_result"]["status"] == "ok"
    assert written["write_result"]["saved_count"] == 9
    docs = store[("metadata_driven_agent_v2", "agent_v2_table_catalog_items")]
    assert set(docs) >= {"table_catalog:production_today", "table_catalog:wip_today", "table_catalog:hold_history"}
    assert docs["table_catalog:hold_history"]["payload"]["required_params"] == ["LOT_ID"]
    assert docs["table_catalog:hold_history"]["payload"]["default_detail_columns"] == [
        "LOT_ID",
        "HOLD_TM",
        "HOLD_CD",
        "HOLD_DESC",
        "HOLD_USER_ID",
        "EVENT_CD",
    ]


def test_worker_single_table_text_input_saves_hold_history(monkeypatch: Any) -> None:
    data = read_json("metadata/table_catalog.json")
    item = {"dataset_key": "hold_history", "payload": data["datasets"]["hold_history"], "confidence": "high"}
    written, store = run_table_authoring_flow(
        "hold_history 데이터셋을 등록할게요. LOT HOLD 이력이고 h_api로 조회하며 LOT_ID가 필수 입력값입니다.",
        [item],
        monkeypatch,
    )

    assert written["write_result"]["status"] == "ok"
    assert written["write_result"]["saved_count"] == 1
    docs = store[("metadata_driven_agent_v2", "agent_v2_table_catalog_items")]
    assert docs["table_catalog:hold_history"]["payload"]["source_type"] == "h_api"


def test_worker_bulk_filter_text_input_saves_all_current_filters(monkeypatch: Any) -> None:
    items = filter_items_from_current_metadata()
    written, store = run_filter_authoring_flow(FILTER_BULK_TEXT, items, monkeypatch)

    assert written["raw_text"] == FILTER_BULK_TEXT
    assert written["write_result"]["status"] == "ok"
    assert written["write_result"]["saved_count"] == 18
    docs = store[("metadata_driven_agent_v2", "agent_v2_main_flow_filters")]
    assert set(docs) >= {"main_flow_filter:DATE", "main_flow_filter:LOT_ID", "main_flow_filter:EQP_MODEL"}
    assert docs["main_flow_filter:DATE"]["payload"]["semantic_role"] == "date"


def test_worker_single_filter_text_input_saves_eqp_model(monkeypatch: Any) -> None:
    item = next(item for item in filter_items_from_current_metadata() if item["filter_key"] == "EQP_MODEL")
    written, store = run_filter_authoring_flow(
        "EQP_MODEL 필터를 등록할게요. 장비 모델을 뜻하고 후보 컬럼은 EQP_MODEL입니다.",
        [item],
        monkeypatch,
    )

    assert written["write_result"]["status"] == "ok"
    assert written["write_result"]["saved_count"] == 1
    docs = store[("metadata_driven_agent_v2", "agent_v2_main_flow_filters")]
    assert docs["main_flow_filter:EQP_MODEL"]["payload"]["column_candidates"] == ["EQP_MODEL"]
