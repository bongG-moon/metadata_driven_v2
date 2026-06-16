# Metadata QA Flow Connection Guide

`metadata_qa_flow`는 등록된 데이터 카탈로그, query template, 활용 예시, domain metadata, greeting/help 질문만 답합니다. 실제 제조 데이터 조회, pandas 분석, MongoDB result 저장은 하지 않습니다.

## Sequence

```text
Backend orchestrator
-> 00 Metadata QA Request Loader
-> 01 Metadata Context Loader
-> 02 Metadata QA Response Builder
-> 03 Metadata QA Message Adapter
-> Chat Output

parallel:
02 Metadata QA Response Builder -> 04 Metadata QA API Response Builder -> API/Data Output
```

## Required Inputs

`00 Metadata QA Request Loader`에는 router 결과를 같이 넘깁니다.

| Input | Value |
| --- | --- |
| `question` | 사용자 질문 |
| `session_id` | 현재 세션 |
| `state` | 이전 compact state |
| `metadata_route` | router_flow의 `flow_inputs.metadata_route` |
| `metadata` | router_flow에서 이미 로드한 metadata가 있으면 전달 가능 |
| `router_payload` | 전체 route decision payload |

`metadata_route.route`가 `direct_answer` 또는 `metadata_qa`일 때만 이 flow를 호출합니다.

## Supported Actions

| metadata_action | Behavior |
| --- | --- |
| `greeting` / `help` | 간단한 안내와 예시 질문 |
| `catalog_list` | 조회 가능한 dataset 목록 |
| `dataset_examples` | 특정 dataset 활용 질문 예시 |
| `dataset_detail` | 컬럼, 필터, source type, 필수 파라미터 등 등록 상세 |
| `dataset_query` | 등록된 query template/API 조회 정보 |
| `domain_search` | 등록된 domain/alias/condition 검색 |
