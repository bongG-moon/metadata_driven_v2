from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data


CATALOG_LIST_CUES = [
    "데이터 목록",
    "data list",
    "조회 가능한 data",
    "조회 가능한 데이터",
    "사용 가능한 데이터",
    "사용 가능한 data",
    "등록된 데이터",
    "데이터 리스트",
]
DATASET_QUERY_CUES = ["쿼리", "query", "sql", "조회문"]
DATASET_EXAMPLE_CUES = ["활용 예시", "예시 질문", "질문 예시", "어떤 질문", "무슨 질문", "뭘 물어"]
DATASET_DETAIL_CUES = ["데이터 정보", "dataset 정보", "상세 정보", "컬럼", "필터", "기준일", "source", "소스"]
DOMAIN_SEARCH_CUES = ["관련 등록 정보", "등록된 정보", "등록 정보", "도메인", "정의", "조건", "의미"]
HELP_CUES = ["도움말", "사용법", "뭐 할 수", "무엇을 할 수", "help", "기능"]
GREETING_WORDS = ["안녕", "안녕하세요", "하이", "hello", "hi"]

FAMILY_KEYWORDS = {
    "production": ["생산", "실적", "production"],
    "wip": ["재공", "wip"],
    "target": ["목표", "계획", "target"],
    "lot": ["lot", "롯", "작업대기", "작업중"],
    "hold": ["hold", "홀드"],
    "equipment": ["장비", "설비", "equipment", "eqp"],
    "capacity": ["capacity", "uph", "capa"],
}


def route_metadata_question(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    question = str(request.get("question") or "").strip()
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    datasets = _datasets(metadata)
    dataset_match = _match_dataset(question, datasets)

    action = ""
    confidence = "medium"
    reason = ""
    target_term = ""
    route = "data_analysis"

    if _is_greeting(question):
        route = "direct_answer"
        action = "greeting"
        confidence = "high"
        reason = "인사 또는 짧은 대화형 입력입니다."
    elif _contains_any(question, CATALOG_LIST_CUES):
        route = "metadata_qa"
        action = "catalog_list"
        confidence = "high"
        reason = "등록된 데이터 목록을 요청했습니다."
    elif _contains_any(question, DATASET_QUERY_CUES):
        route = "metadata_qa"
        action = "dataset_query"
        confidence = "high" if dataset_match.get("target_dataset") else "medium"
        reason = "특정 데이터셋의 조회 쿼리/SQL 정보를 요청했습니다."
    elif _contains_any(question, DATASET_EXAMPLE_CUES):
        route = "metadata_qa"
        action = "dataset_examples"
        confidence = "high" if dataset_match.get("target_dataset") or dataset_match.get("target_family") else "medium"
        reason = "데이터셋별 활용 예시 질문을 요청했습니다."
    elif dataset_match.get("target_dataset") and _contains_any(question, DATASET_DETAIL_CUES):
        route = "metadata_qa"
        action = "dataset_detail"
        confidence = "high"
        reason = "특정 데이터셋의 등록 상세 정보를 요청했습니다."
    elif _contains_any(question, HELP_CUES) and not dataset_match.get("target_dataset"):
        route = "direct_answer"
        action = "help"
        confidence = "high"
        reason = "에이전트 사용법 또는 기능 안내를 요청했습니다."
    elif _contains_any(question, DOMAIN_SEARCH_CUES):
        route = "metadata_qa"
        action = "domain_search"
        confidence = "medium"
        reason = "도메인 메타데이터에서 관련 등록 정보를 찾아야 하는 질문입니다."
        target_term = _extract_domain_term(question, dataset_match)
    elif dataset_match.get("target_dataset") and _contains_any(question, ["정보", "상세"]):
        route = "metadata_qa"
        action = "dataset_detail"
        confidence = "medium"
        reason = "특정 데이터셋 정보 확인 질문으로 판단했습니다."

    next_payload = deepcopy(payload)
    next_payload["metadata_route"] = {
        "route": route,
        "metadata_action": action,
        "target_dataset": dataset_match.get("target_dataset", ""),
        "target_family": dataset_match.get("target_family", ""),
        "target_term": target_term,
        "confidence": confidence,
        "reason": reason or "일반 데이터 분석 질문으로 판단했습니다.",
        "dataset_matches": dataset_match.get("matches", []),
    }
    return next_payload


def _match_dataset(question: str, datasets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    q_lower = question.lower()
    q_norm = _normalize(question)
    matches: list[dict[str, Any]] = []
    for key, item in datasets.items():
        display = str(item.get("display_name") or "")
        candidates = [key, display]
        for candidate in candidates:
            text = str(candidate or "")
            if not text:
                continue
            if text.lower() in q_lower or _normalize(text) in q_norm:
                matches.append({"dataset_key": key, "display_name": display, "match_type": "dataset"})
                break
    target_dataset = matches[0]["dataset_key"] if matches else ""

    target_family = ""
    if not target_dataset:
        for family, keywords in FAMILY_KEYWORDS.items():
            if _contains_any(question, keywords):
                target_family = family
                matches.append({"dataset_family": family, "match_type": "family"})
                break
    elif isinstance(datasets.get(target_dataset), dict):
        target_family = str(datasets[target_dataset].get("dataset_family") or "")

    return {"target_dataset": target_dataset, "target_family": target_family, "matches": matches[:5]}


def _extract_domain_term(question: str, dataset_match: dict[str, Any]) -> str:
    text = question
    for match in dataset_match.get("matches", []):
        for key in ("dataset_key", "display_name", "dataset_family"):
            value = str(match.get(key) or "")
            if value:
                text = re.sub(re.escape(value), " ", text, flags=re.IGNORECASE)
    replace_terms = [
        "관련해서",
        "관련된",
        "관련",
        "등록된",
        "등록",
        "정보",
        "알려줘",
        "보여줘",
        "도메인",
        "정의",
        "조건",
        "의미",
        "에 대해",
        "대해",
        "와",
        "과",
        "은",
        "는",
        "이",
        "가",
        "?",
    ]
    for term in replace_terms:
        text = text.replace(term, " ")
    return " ".join(part for part in re.split(r"\s+", text.strip()) if part)[:80]


def _is_greeting(question: str) -> bool:
    cleaned = re.sub(r"[\s!?.,~]+", "", question.strip().lower())
    if not cleaned:
        return False
    return cleaned in {word.lower() for word in GREETING_WORDS} or (
        len(cleaned) <= 8 and any(cleaned.startswith(word.lower()) for word in GREETING_WORDS)
    )


def _contains_any(text: str, needles: list[str]) -> bool:
    lower = text.lower()
    normalized = _normalize(text)
    for needle in needles:
        needle_text = str(needle or "")
        if not needle_text:
            continue
        if needle_text.lower() in lower or _normalize(needle_text) in normalized:
            return True
    return False


def _normalize(text: Any) -> str:
    return re.sub(r"[\s\-_/.]+", "", str(text or "").lower())


def _datasets(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    table_catalog = metadata.get("table_catalog") if isinstance(metadata.get("table_catalog"), dict) else {}
    datasets = table_catalog.get("datasets") if isinstance(table_catalog.get("datasets"), dict) else {}
    return {str(key): item for key, item in datasets.items() if isinstance(item, dict)}


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


class MetadataQuestionRouter(Component):
    display_name = "00 Metadata Question Router"
    description = "Classifies greeting, catalog, dataset-info, query-template, and domain-metadata questions before data analysis."
    icon = "Route"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        result = route_metadata_question(getattr(self, "payload", None))
        route = result.get("metadata_route", {})
        self.status = {
            "route": route.get("route"),
            "metadata_action": route.get("metadata_action"),
            "target_dataset": route.get("target_dataset"),
            "confidence": route.get("confidence"),
        }
        return Data(data=result)
