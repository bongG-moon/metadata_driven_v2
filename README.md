# Metadata Driven Langflow V2

`metadata_driven_v2`는 제조 데이터 질의/분석 Agent를 처음부터 다시 구현할 개발자에게 넘기기 위한 독립 실행형 Langflow 구현본입니다.

구현 기준은 다음 두 문서입니다.

- `docs/METADATA_AUTHORING_FLOW_GUIDE.md`
- `docs/DATA_RETRIEVAL_SOURCES.md`
- `langflow_components/domain_authoring_flow/raw_text_input_example.md`
- `langflow_components/table_catalog_authoring_flow/raw_text_input_example.md`
- `langflow_components/main_flow_filters_authoring_flow/raw_text_input_example.md`

핵심 흐름은 아래 계약을 따릅니다.

```text
state -> metadata load -> intent plan -> retrieval routing -> retrieval -> pandas postprocess -> final answer/state
```

메타데이터/도움말/카탈로그 질문은 intent plan 전에 별도 라우팅합니다. `03`는 metadata 기반 후보 컨텍스트만 만들고, 작은 route-classifier LLM이 질문 유형 기준으로 metadata QA인지 실제 데이터 분석인지 판정합니다.

## 폴더 구조

| path | 설명 |
| --- | --- |
| `metadata/` | domain, table catalog, main flow filter, regression question seed |
| `reference_runtime/` | Langflow 없이 로컬에서 검증하는 Python reference runtime |
| `langflow_components/main_flow/` | 메인 Langflow canvas용 standalone custom components |
| `langflow_components/main_flow/09~14_*_retriever.py` | source_type별 retriever components |
| `langflow_components/*_authoring_flow/` | 자연어 metadata authoring flows |
| `sample_data/` | dummy/source 검증용 fixture |
| `tools/` | 실행, 검증, MongoDB 업로드 스크립트 |
| `tests/` | runtime, component contract, LLM-node-style flow tests |
| `docs/` | 구현/연결/운영/검증 가이드 |

## Recommended Split Runtime

신규 운영 기준은 combined `main_flow`가 아니라 backend orchestrator가 flow를 분기 호출하는 구조입니다.

```text
Web/API
-> router_flow
-> backend orchestrator
-> metadata_qa_flow | data_analysis_flow | report_generation_flow | operations_diagnosis_flow
```

- `router_flow/`: 질문 유형을 분류하고 `selected_flow`를 반환합니다.
- `metadata_qa_flow/`: 조회 가능한 데이터 목록, query template, 활용 예시, domain 정보, greeting/help를 답합니다.
- `data_analysis_flow/`: 실제 source 조회, pandas 분석, MongoDB result store, 최종 답변을 담당합니다.
- `report_generation_flow/`: 리포트 생성 요청 확장 flow입니다.
- `operations_diagnosis_flow/`: 운영 이상/병목 진단 요청 확장 flow입니다.
- `main_flow/`: 기존 단일 canvas 배포를 위한 compatibility flow입니다.

## Main Flow

Langflow canvas에서는 LLM node를 중간에 명시적으로 둡니다.

```text
Chat Input
-> 00 Request State Loader
-> 02 Metadata Context Loader
-> 03 Route Candidate Builder
-> 04 Route Classifier Prompt Builder
-> Route Classifier LLM (question-type route)
-> 05 Route Classifier Normalizer
-> 06 Metadata QA Response Builder
-> 07 Intent Prompt Builder
-> Gemini/LLM Intent JSON
-> 08 Intent Plan Normalizer
-> 01 MongoDB Data Loader (restore previous result rows only when needed; internal mode=auto)
-> 09~14 main_flow retriever nodes
-> 15 Retrieval Payload Adapter
-> 16 Pandas Prompt Builder
-> Gemini/LLM Pandas Code JSON
-> 17 Pandas Code Executor
-> 18 MongoDB Data Store
-> 19 Answer Prompt Builder
-> Gemini/LLM Final Answer
-> 20 Answer Response Builder
-> 21 Answer Message Adapter
-> Chat Output
```

각 component 파일은 Langflow Desktop에 하나씩 붙여 넣어도 동작하도록 sibling helper import 없이 작성되어 있습니다.

## 빠른 검증

```powershell
cd C:\Users\qkekt\Desktop\metadata_driven_v2
python -m compileall -q reference_runtime langflow_components tools tests
python -m pytest tests -q
python tools\validate_regression.py
python tools\upload_json_to_mongodb.py --dry-run
```

실제 LLM 검증은 `.env`의 Gemini/MongoDB 설정을 사용합니다.

```powershell
python tools\validate_env.py
python tools\validate_gemini_connection.py
python tools\validate_llm_in_loop.py --limit 1
python tools\validate_llm_in_loop.py
```

## 주요 검증 질문

`metadata/regression_questions.json`에는 현재 필수 회귀 질문 16개가 들어 있습니다. 검증 범위는 단순 답변 문구가 아니라 아래 계약입니다.

- intent type과 analysis kind
- 사용 dataset과 source별 date/filter scope
- DA/WB 같은 공정 그룹 확장
- LPDDR5/HBM 같은 제품 조건 적용
- lot count는 `LOT_ID.nunique()` 사용
- follow-up state 사용 및 scope reset
- production/wip/target join과 achievement/balance 계산
- pandas code JSON 생성, AST guardrail, in-memory frame 실행

검증 결과는 `validation_runs/<timestamp>/REPORT.md`와 `results.json`에 저장됩니다.

## MongoDB

Main flow result rows use a separate full-name collection, `MONGODB_RESULT_COLLECTION` (default `agent_v2_result_store`).
If the caller passes compact previous `state.current_data` with preview rows, row count, columns, `data_ref`, and product key summary, `00 Request State Loader` is enough before metadata loading.
In `data_analysis_flow`, `04 Previous Result Restore Router` decides whether full previous rows are needed. Backend or Langflow branch logic should call `05 MongoDB Data Loader` only when `previous_result_restore.required=true`; `06 Previous Result Restore Merger` then merges the optional loader branch back into the main payload.
When a follow-up question must recalculate, filter, sort, regroup, or show detail rows from the previous result itself, `03 Intent Plan Normalizer` sets `requires_full_state_hydrate=true` or `state_hydrate_mode=full`.
`16 MongoDB Data Store` writes both source `runtime_sources` and pandas `analysis.rows` right after pandas execution, then leaves preview rows plus MongoDB `data_ref` pointers in the payload.
Follow-up product context is carried in `state.current_data.product_key_values`, so product-key follow-ups do not need to load full previous rows.

`.env`는 원본 workspace에서 복사되어 있습니다. MongoDB metadata는 prefix로 collection을 조합하지 않고 full collection name 3개를 그대로 입력합니다. 기본값은 `MONGODB_DATABASE=metadata_driven_agent_v2`, `MONGODB_DOMAIN_COLLECTION=agent_v2_domain_items`, `MONGODB_TABLE_CATALOG_COLLECTION=agent_v2_table_catalog_items`, `MONGODB_MAIN_FLOW_FILTER_COLLECTION=agent_v2_main_flow_filters`입니다.

업로드 전 dry-run으로 collection과 document count를 확인하세요.

```powershell
python tools\upload_json_to_mongodb.py --dry-run
```

현장 작업자가 JSON을 직접 올리는 대신 자연어로 metadata를 등록하는 경우에는 각 authoring flow 폴더의 `raw_text_input_example.md` 예시 문장을 해당 flow 입력으로 사용하세요.

## Langflow 연결 문서

- `langflow_components/domain_authoring_flow/raw_text_input_example.md` - 업무 용어 metadata 입력 예시
- `langflow_components/table_catalog_authoring_flow/raw_text_input_example.md` - 데이터셋/table catalog metadata 입력 예시
- `langflow_components/main_flow_filters_authoring_flow/raw_text_input_example.md` - main flow filter metadata 입력 예시
- `docs/V2_BASE_COMPLETION_REPORT_20260613.md` - v2 base 보강 내역과 최신 검증 결과
- `docs/V2_LANGFLOW_CANVAS_WIRING_GUIDE.md` - main flow, retrieval flow, authoring flow의 output/input 연결 전체표
- `langflow_components/router_flow/CONNECTION_GUIDE.md`
- `langflow_components/metadata_qa_flow/CONNECTION_GUIDE.md`
- `langflow_components/data_analysis_flow/CONNECTION_GUIDE.md`
- `langflow_components/report_generation_flow/CONNECTION_GUIDE.md`
- `langflow_components/operations_diagnosis_flow/CONNECTION_GUIDE.md`
- `langflow_components/main_flow/CONNECTION_GUIDE.md`
- `langflow_components/domain_authoring_flow/CONNECTION_GUIDE.md`
- `langflow_components/table_catalog_authoring_flow/CONNECTION_GUIDE.md`
- `langflow_components/main_flow_filters_authoring_flow/CONNECTION_GUIDE.md`
- `docs/LANGFLOW_NODE_CONNECTION_GUIDE.md`
- `docs/LANGFLOW_IMPLEMENTATION_GUIDE.md`
- `docs/WEB_IMPLEMENTATION_GUIDE.md` - main flow와 metadata authoring flow를 업무 web으로 감싸기 위한 구현 요구사항


