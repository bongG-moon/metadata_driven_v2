# Metadata Driven Langflow V2

`metadata_driven_v2`는 제조 데이터 질의/분석 Agent를 처음부터 다시 구현할 개발자에게 넘기기 위한 독립 실행형 Langflow 구현본입니다.

구현 기준은 다음 두 문서입니다.

- `docs/METADATA_AUTHORING_FLOW_GUIDE.md`
- `docs/DATA_RETRIEVAL_SOURCES.md`
- `docs/METADATA_TEXT_INPUT_EXAMPLES.md`

핵심 흐름은 아래 계약을 따릅니다.

```text
state -> metadata load -> intent plan -> retrieval routing -> retrieval -> pandas postprocess -> final answer/state
```

## 폴더 구조

| path | 설명 |
| --- | --- |
| `metadata/` | domain, table catalog, main flow filter, regression question seed |
| `reference_runtime/` | Langflow 없이 로컬에서 검증하는 Python reference runtime |
| `langflow_components/main_flow/` | 메인 Langflow canvas용 standalone custom components |
| `langflow_components/data_retrieval_flow/` | source_type별 standalone retriever components |
| `langflow_components/*_authoring_flow/` | 자연어 metadata authoring flows |
| `sample_data/` | dummy/source 검증용 fixture |
| `tools/` | 실행, 검증, MongoDB 업로드 스크립트 |
| `tests/` | runtime, component contract, LLM-node-style flow tests |
| `docs/` | 구현/연결/운영/검증 가이드 |

## Main Flow

Langflow canvas에서는 LLM node를 중간에 명시적으로 둡니다.

```text
Chat Input
-> 00 Request State Loader
-> 01 Metadata Context Loader
-> 02 Intent Prompt Builder
-> Gemini/LLM Intent JSON
-> 03 Intent Plan Normalizer
-> data retrieval flow
-> 04 Retrieval Payload Adapter
-> 05 Pandas Prompt Builder
-> Gemini/LLM Pandas Code JSON
-> 06 Pandas Code Executor
-> 07 Answer Prompt Builder
-> Gemini/LLM Final Answer
-> 08 Answer Response Builder
-> 09 Answer Message Adapter
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

`.env`는 원본 workspace에서 복사되어 있습니다. MongoDB metadata는 prefix로 collection을 조합하지 않고 full collection name 3개를 그대로 입력합니다. 기본값은 `MONGODB_DATABASE=metadata_driven_agent_v2`, `MONGODB_DOMAIN_COLLECTION=agent_v2_domain_items`, `MONGODB_TABLE_CATALOG_COLLECTION=agent_v2_table_catalog_items`, `MONGODB_MAIN_FLOW_FILTER_COLLECTION=agent_v2_main_flow_filters`입니다.

업로드 전 dry-run으로 collection과 document count를 확인하세요.

```powershell
python tools\upload_json_to_mongodb.py --dry-run
```

현장 작업자가 JSON을 직접 올리는 대신 자연어로 metadata를 등록하는 경우에는 `docs/METADATA_TEXT_INPUT_EXAMPLES.md`의 예시 문장을 authoring flow 입력으로 사용하세요.

## Langflow 연결 문서

- `docs/METADATA_TEXT_INPUT_EXAMPLES.md` - 제조 작업자용 자연어 metadata 입력 예시와 검증 방법
- `docs/V2_BASE_COMPLETION_REPORT_20260613.md` - v2 base 보강 내역과 최신 검증 결과
- `docs/V2_LANGFLOW_CANVAS_WIRING_GUIDE.md` - main flow, retrieval flow, authoring flow의 output/input 연결 전체표
- `langflow_components/main_flow/CONNECTION_GUIDE.md`
- `langflow_components/data_retrieval_flow/CONNECTION_GUIDE.md`
- `langflow_components/domain_authoring_flow/CONNECTION_GUIDE.md`
- `langflow_components/table_catalog_authoring_flow/CONNECTION_GUIDE.md`
- `langflow_components/main_flow_filters_authoring_flow/CONNECTION_GUIDE.md`
- `docs/LANGFLOW_NODE_CONNECTION_GUIDE.md`
- `docs/LANGFLOW_IMPLEMENTATION_GUIDE.md`
