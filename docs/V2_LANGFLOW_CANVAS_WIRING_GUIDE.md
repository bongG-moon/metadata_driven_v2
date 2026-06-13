# V2 Langflow Canvas Wiring Guide

이 문서는 `metadata_driven_v2`를 Langflow canvas에 연결할 때 기준으로 삼는 가이드입니다.
현재 v2 main flow는 metadata collection뿐 아니라 row result store도 full collection name을 직접 입력하는 구조입니다.

## 1. Main Query/Analysis Flow

### 1.1 Node 목록

| 순서 | Langflow node 이름 | Component file | 주요 역할 |
| --- | --- | --- | --- |
| Input | Chat Input | Langflow 기본 node | 사용자 질문 입력 |
| 00 | 00 Request State Loader | `langflow_components/main_flow/00_request_state_loader.py` | 질문, session id, 이전 state를 compact payload로 변환 |
| 01 | 01 Metadata Context Loader | `langflow_components/main_flow/01_metadata_context_loader.py` | MongoDB metadata 로드 |
| 02 | 02 Intent Prompt Builder | `langflow_components/main_flow/02_intent_prompt_builder.py` | intent JSON 생성을 위한 LLM prompt 생성 |
| LLM-A | Gemini/LLM Intent JSON | Langflow 기본 Gemini/LLM node | intent JSON 생성 |
| 03 | 03 Intent Plan Normalizer | `langflow_components/main_flow/03_intent_plan_normalizer.py` | intent JSON 정규화, retrieval_jobs 생성/보강 |
| Retrieval | Data Retrieval Flow | 아래 2장 참고 | source_type별 데이터 조회 |
| 04 | 04 Retrieval Payload Adapter | `langflow_components/main_flow/04_retrieval_payload_adapter.py` | retrieval 결과를 `runtime_sources`와 compact `source_results`로 변환 |
| 05 | 05 MongoDB Data Store | `langflow_components/main_flow/05_mongodb_data_store.py` | 큰 row list를 MongoDB result collection에 저장하고 `data_ref`로 축약 |
| 06 | 06 MongoDB Data Loader | `langflow_components/main_flow/06_mongodb_data_loader.py` | MongoDB `data_ref`를 pandas 실행 또는 follow-up planning 전에 rows로 복원 |
| 07 | 07 Pandas Prompt Builder | `langflow_components/main_flow/07_pandas_prompt_builder.py` | pandas code JSON 생성을 위한 LLM prompt 생성 |
| LLM-B | Gemini/LLM Pandas Code JSON | Langflow 기본 Gemini/LLM node | pandas code JSON 생성 |
| 08 | 08 Pandas Code Executor | `langflow_components/main_flow/08_pandas_code_executor.py` | safety check 후 pandas code 실행 |
| 09 | 09 Answer Prompt Builder | `langflow_components/main_flow/09_answer_prompt_builder.py` | 최종 한국어 답변 생성을 위한 LLM prompt 생성 |
| LLM-C | Gemini/LLM Final Answer | Langflow 기본 Gemini/LLM node | 최종 답변 생성 |
| 10 | 10 Answer Response Builder | `langflow_components/main_flow/10_answer_response_builder.py` | answer, data, applied_scope, next state 조립 |
| 11 | 11 Answer Message Adapter | `langflow_components/main_flow/11_answer_message_adapter.py` | Playground 출력용 Markdown message 생성 |
| Output | Chat Output | Langflow 기본 node | 최종 답변 출력 |

### 1.2 필수 연결

| # | From node | From output | To node | To input | 설명 |
| --- | --- | --- | --- | --- | --- |
| 1 | Chat Input | `message` 또는 `text` | 00 Request State Loader | `question` | 사용자 질문 |
| 2 | Text Input | value | 00 Request State Loader | `session_id` | 예: `demo-session`, 사용자별 session key 권장 |
| 3 | State Store 또는 이전 final payload | `state` data | 00 Request State Loader | `state` | 선택. follow-up이면 필요 |
| 4 | 00 Request State Loader | `payload` | 06 MongoDB Data Loader | `payload` | 이전 state의 compact `data_ref` 복원 |
| 5 | 06 MongoDB Data Loader | `payload_out` | 01 Metadata Context Loader | `payload` | metadata 로드 전 state hydrate |
| 6 | Text/Secret Input | value | 01 Metadata Context Loader | `mongo_uri` | MongoDB 사용 시 필요 |
| 7 | Text Input | value | 01 Metadata Context Loader | `mongo_database` | 기본값 예: `metadata_driven_agent_v2` |
| 8 | Text Input 3개 | value | 01 Metadata Context Loader | `domain_collection_name`, `table_catalog_collection_name`, `main_flow_filter_collection_name` | full collection name 입력 |
| 9 | Text Input | value | 05 MongoDB Data Store, 06 MongoDB Data Loader | `result_collection_name` | full collection name 입력. 기본 `agent_v2_result_store` |
| 10 | 01 Metadata Context Loader | `payload_out` | 02 Intent Prompt Builder | `payload` | metadata 포함 payload |
| 11 | 02 Intent Prompt Builder | `intent_prompt` | LLM-A Gemini/LLM Intent JSON | prompt/message input | JSON-only 응답 권장 |
| 12 | 01 Metadata Context Loader | `payload_out` | 03 Intent Plan Normalizer | `payload` | LLM 응답과 결합할 payload |
| 13 | LLM-A Gemini/LLM Intent JSON | text/message output | 03 Intent Plan Normalizer | `llm_response` | intent JSON 응답 |
| 14 | 03 Intent Plan Normalizer | `payload_out` | Data Retrieval Flow start node(s) | `payload` | 아래 2장 중 하나 선택 |
| 15 | 03 Intent Plan Normalizer | `payload_out` | 04 Retrieval Payload Adapter | `main_payload` | main payload branch |
| 16 | Data Retrieval Flow end | `retrieval_payload` | 04 Retrieval Payload Adapter | `retrieval_payload` | source 조회 결과 병합 |
| 17 | 04 Retrieval Payload Adapter | `payload` | 05 MongoDB Data Store | `payload` | source rows 저장 및 ref compact |
| 18 | 05 MongoDB Data Store | `payload_out` | 06 MongoDB Data Loader | `payload` | pandas 직전 rows 복원 |
| 19 | 06 MongoDB Data Loader | `payload_out` | 07 Pandas Prompt Builder | `payload` | pandas prompt 생성 |
| 20 | 07 Pandas Prompt Builder | `pandas_prompt` | LLM-B Gemini/LLM Pandas Code JSON | prompt/message input | JSON-only 응답 필수 |
| 21 | 06 MongoDB Data Loader | `payload_out` | 08 Pandas Code Executor | `payload` | code 실행용 source rows payload |
| 22 | LLM-B Gemini/LLM Pandas Code JSON | text/message output | 08 Pandas Code Executor | `llm_response` | pandas code JSON 응답 |
| 23 | 08 Pandas Code Executor | `payload_out` | 09 Answer Prompt Builder | `payload` | 최종 답변 prompt 생성 |
| 24 | 09 Answer Prompt Builder | `answer_prompt` | LLM-C Gemini/LLM Final Answer | prompt/message input | plain Korean text 또는 JSON 가능 |
| 25 | 08 Pandas Code Executor | `payload_out` | 10 Answer Response Builder | `payload` | 답변/state 조립용 payload |
| 26 | LLM-C Gemini/LLM Final Answer | text/message output | 10 Answer Response Builder | `llm_response` | 최종 답변 |
| 27 | 10 Answer Response Builder | `payload_out` | 05 MongoDB Data Store | `payload` | final `data.rows`와 `state.current_data.rows` compact |
| 28 | 05 MongoDB Data Store | `payload_out` | 11 Answer Message Adapter | `payload` | Playground 출력용 message 생성 |
| 29 | 11 Answer Message Adapter | `message` | Chat Output | `message` | 사용자에게 보일 최종 출력 |
| 30 | 05 MongoDB Data Store after #27 | `payload_out.state` | State Store | stored state | 다음 질문의 00 `state` input으로 재사용 |

### 1.3 MongoDB Result Store 입력 의미

| 입력 | 의미 | 운영 기준 |
| --- | --- | --- |
| `mongo_uri` | MongoDB 접속 URI | 비워두면 `MONGODB_URI` 사용 |
| `mongo_database` | database 이름 | 비워두면 `MONGODB_DATABASE` 사용 |
| `result_collection_name` | row payload 저장용 full collection name | 기본 `agent_v2_result_store`, prefix 조합 없음 |
| `enabled` | 저장/조회 사용 여부 | 운영은 `true`, 로컬 단위 테스트는 `false` 가능 |
| `preview_row_limit` | payload에 남길 preview row 수 | 기본 5 |
| `min_rows` | 이 row 수 이상이면 MongoDB에 저장 | 기본 1 |

## 2. Data Retrieval Flow

### 2.1 로컬/dummy 검증용 연결

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| D1 | 03 Intent Plan Normalizer | `payload_out` | 01 Dummy Data Retriever | `payload` |
| D2 | 01 Dummy Data Retriever | `retrieval_payload` | 04 Retrieval Payload Adapter | `retrieval_payload` |

`Source Retrieval Merger`는 생략해도 됩니다.

### 2.2 source_type별 운영 연결

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| R1 | 03 Intent Plan Normalizer | `payload_out` | 02 Oracle Query Retriever | `payload` |
| R2 | 03 Intent Plan Normalizer | `payload_out` | 03 H-API Retriever | `payload` |
| R3 | 03 Intent Plan Normalizer | `payload_out` | 04 Datalake Retriever | `payload` |
| R4 | 03 Intent Plan Normalizer | `payload_out` | 05 Goodocs Retriever | `payload` |
| R5 | 02 Oracle Query Retriever | `retrieval_payload` | 06 Source Retrieval Merger | `oracle_retrieval` |
| R6 | 03 H-API Retriever | `retrieval_payload` | 06 Source Retrieval Merger | `h_api_retrieval` |
| R7 | 04 Datalake Retriever | `retrieval_payload` | 06 Source Retrieval Merger | `datalake_retrieval` |
| R8 | 05 Goodocs Retriever | `retrieval_payload` | 06 Source Retrieval Merger | `goodocs_retrieval` |
| R9 | 06 Source Retrieval Merger | `retrieval_payload` | 04 Retrieval Payload Adapter | `retrieval_payload` |

`source_results[]`는 최소한 `dataset_key`, `source_alias`, `source_type`, `data`, `columns`, `row_count`, `applied_params`, `applied_filters`를 맞추는 것이 좋습니다.

## 3. Follow-up State 연결

follow-up 질문을 처리하려면 #29 이후 compact된 payload의 `state`를 다음 turn의 00 `state` input으로 다시 넣습니다.

State에 들어가는 핵심 값:

- `chat_history`
- `context.last_intent_type`
- `context.last_analysis_kind`
- `context.last_source_aliases`
- `current_data.columns`
- `current_data.rows` 또는 MongoDB `current_data.data_ref`
- `current_data.source_dataset_keys`
- `followup_source_results`

다음 turn 시작 시 `00 Request State Loader -> 06 MongoDB Data Loader -> 01 Metadata Context Loader` 순서로 연결하면 compact된 `current_data.data_ref`가 다시 rows로 복원됩니다.

## 4. Metadata Authoring Flow 공통 연결

아래 세 flow는 같은 패턴을 사용합니다.

- Domain: `langflow_components/domain_authoring_flow/`
- Table catalog: `langflow_components/table_catalog_authoring_flow/`
- Main flow filter: `langflow_components/main_flow_filters_authoring_flow/`

| 순서 | 역할 | Domain node | Table node | Filter node |
| --- | --- | --- | --- | --- |
| 00 | 자연어 요청 + Mongo 설정 로드 | 00 Domain Authoring Request Loader | 00 Table Catalog Authoring Request Loader | 00 Main Flow Filter Authoring Request Loader |
| 01 | 정제 prompt 생성 | 01 Domain Text Refinement Prompt Builder | 01 Table Catalog Text Refinement Prompt Builder | 01 Main Flow Filter Text Refinement Prompt Builder |
| LLM-1 | 자연어 정제 | Gemini/LLM refinement | Gemini/LLM refinement | Gemini/LLM refinement |
| 02 | 정제 결과 반영 | 02 Domain Text Refinement Normalizer | 02 Table Catalog Text Refinement Normalizer | 02 Main Flow Filter Text Refinement Normalizer |
| 03 | 저장 후보 JSON prompt 생성 | 03 Domain Authoring Prompt Builder | 03 Table Catalog Authoring Prompt Builder | 03 Main Flow Filter Authoring Prompt Builder |
| LLM-2 | 저장 후보 JSON 생성 | Gemini/LLM authoring JSON | Gemini/LLM authoring JSON | Gemini/LLM authoring JSON |
| 04 | 저장 후보 JSON 정규화 | 04 Domain Authoring Result Normalizer | 04 Table Catalog Authoring Result Normalizer | 04 Main Flow Filter Authoring Result Normalizer |
| 05 | 중복/유사성 평가 | 05 Domain Similarity Checker | 05 Table Catalog Similarity Checker | 05 Main Flow Filter Similarity Checker |
| 06 | 저장 전 review prompt 생성 | 06 Domain Review Prompt Builder | 06 Table Catalog Review Prompt Builder | 06 Main Flow Filter Review Prompt Builder |
| LLM-3 | 저장 가능 여부 review | Gemini/LLM review JSON | Gemini/LLM review JSON | Gemini/LLM review JSON |
| 07 | MongoDB writer | 07 Domain Review Writer | 07 Table Catalog Review Writer | 07 Main Flow Filter Review Writer |
| 08 | 최종 응답 | 08 Domain Authoring Response Builder | 08 Table Catalog Authoring Response Builder | 08 Main Flow Filter Authoring Response Builder |

Authoring flow도 collection prefix를 쓰지 않습니다. `collection_name`에는 `agent_v2_domain_items`, `agent_v2_table_catalog_items`, `agent_v2_main_flow_filters` 같은 full collection name을 직접 입력합니다.

## 5. 구현 후 확인 순서

```powershell
cd C:\Users\qkekt\Desktop\metadata_driven_v2
python -m compileall -q reference_runtime langflow_components tools tests
python -m pytest tests -q
python tools\validate_regression.py
python tools\upload_json_to_mongodb.py --dry-run
python tools\validate_llm_in_loop.py --limit 1
```

Langflow canvas에서는 MongoDB metadata collection 3개가 준비된 상태에서 dummy retrieval, result store `enabled=false`로 wiring을 먼저 검증하고, 그 다음 result store `enabled=true`, live source credential 순서로 확장하는 것을 권장합니다.
