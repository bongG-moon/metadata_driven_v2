# V2 Langflow Canvas Wiring Guide
> Compatibility note: this guide describes the combined `main_flow` canvas. New runtime wiring should use `router_flow` plus the selected subflow guides in `langflow_components/*_flow/CONNECTION_GUIDE.md`.

이 문서는 `metadata_driven_v2`를 Langflow canvas에 연결할 때 기준으로 삼는 가이드입니다.
현재 v2 main flow는 metadata collection뿐 아니라 row result store도 full collection name을 직접 입력하는 구조입니다.
`metadata_route.target_dataset`은 metadata QA에서 특정 dataset의 설명/쿼리/활용 예시를 답하기 위한 대상 포인터입니다. 일반 데이터 분석 질문의 조회 dataset은 이후 `07 Intent Prompt Builder`와 `08 Intent Plan Normalizer`에서 별도로 결정합니다.

## 1. Main Query/Analysis Flow

### 1.1 Node 목록

| 순서 | Langflow node 이름 | Component file | 주요 역할 |
| --- | --- | --- | --- |
| Input | Chat Input | Langflow 기본 node | 사용자 질문 입력 |
| 00 | 00 Request State Loader | `langflow_components/main_flow/00_request_state_loader.py` | 질문, session id, 이전 state를 compact payload로 변환 |
| 01 | 01 MongoDB Data Loader | `langflow_components/main_flow/01_mongodb_data_loader.py` | optional. 이전 state에 `data_ref`만 있고 preview/summary가 없을 때 preview 복원 |
| 02 | 02 Metadata Context Loader | `langflow_components/main_flow/02_metadata_context_loader.py` | MongoDB metadata 로드 |
| 03 | 03 Route Candidate Builder | `langflow_components/main_flow/03_route_candidate_builder.py` | metadata 기반 dataset/family/quantity 후보 컨텍스트 생성 |
| 04 | 04 Route Classifier Prompt Builder | `langflow_components/main_flow/04_route_classifier_prompt_builder.py` | 질문 유형 기준 route 분류 prompt 생성 |
| LLM-R | Route Classifier LLM | Langflow 기본 Gemini/LLM node | metadata QA인지 실제 데이터 분석인지 route JSON 생성 |
| 05 | 05 Route Classifier Normalizer | `langflow_components/main_flow/05_route_classifier_normalizer.py` | LLM route 결과 정규화 |
| 06 | 06 Metadata QA Response Builder | `langflow_components/main_flow/06_metadata_qa_response_builder.py` | metadata 직접 답변 또는 분석 질문 pass-through |
| 07 | 07 Intent Prompt Builder | `langflow_components/main_flow/07_intent_prompt_builder.py` | intent JSON 생성을 위한 LLM prompt 생성 |
| LLM-A | Gemini/LLM Intent JSON | Langflow 기본 Gemini/LLM node | intent JSON 생성 |
| 08 | 08 Intent Plan Normalizer | `langflow_components/main_flow/08_intent_plan_normalizer.py` | intent JSON 정규화, retrieval_jobs 생성/보강 |
| 08B | 01 MongoDB Data Loader | `langflow_components/main_flow/01_mongodb_data_loader.py` | `restore_mode=auto`로 필요한 후속 분석만 이전 결과 전체 rows 복원 |
| Retrieval | Main flow retriever nodes | `langflow_components/main_flow/09`~`14` | source_type별 데이터 조회 및 병합 |
| 15 | 15 Retrieval Payload Adapter | `langflow_components/main_flow/15_retrieval_payload_adapter.py` | retrieval 결과를 `runtime_sources`와 compact `source_results`로 변환 |
| 16 | 16 Pandas Prompt Builder | `langflow_components/main_flow/16_pandas_prompt_builder.py` | pandas code JSON 생성을 위한 LLM prompt 생성 |
| LLM-B | Gemini/LLM Pandas Code JSON | Langflow 기본 Gemini/LLM node | pandas code JSON 생성 |
| 17 | 17 Pandas Code Executor | `langflow_components/main_flow/17_pandas_code_executor.py` | safety check 후 pandas code 실행 |
| 18 | 18 MongoDB Data Store | `langflow_components/main_flow/18_mongodb_data_store.py` | source `runtime_sources`와 pandas `analysis.rows`를 MongoDB result collection에 저장하고 `data_ref`로 축약 |
| 19 | 19 Answer Prompt Builder | `langflow_components/main_flow/19_answer_prompt_builder.py` | 최종 한국어 답변 생성을 위한 LLM prompt 생성 |
| LLM-C | Gemini/LLM Final Answer | Langflow 기본 Gemini/LLM node | 최종 답변 생성 |
| 20 | 20 Answer Response Builder | `langflow_components/main_flow/20_answer_response_builder.py` | answer, data, applied_scope, next state 조립 |
| 21 | 21 Answer Message Adapter | `langflow_components/main_flow/21_answer_message_adapter.py` | Playground 출력용 Markdown message 생성 |
| Output | Chat Output | Langflow 기본 node | 최종 답변 출력 |

### 1.2 필수 연결

| # | From node | From output | To node | To input | 설명 |
| --- | --- | --- | --- | --- | --- |
| 1 | Chat Input | `message` 또는 `text` | 00 Request State Loader | `question` | 사용자 질문 |
| 2 | Text Input | value | 00 Request State Loader | `session_id` | 예: `demo-session`, 사용자별 session key 권장 |
| 3 | State Store 또는 이전 final payload | `state` data | 00 Request State Loader | `state` | 선택. follow-up이면 필요 |
| 4 | 00 Request State Loader | `payload` | 02 Metadata Context Loader | `payload` | compact state에 preview/summary가 있으면 기본 경로 |
| 4B | 00 Request State Loader | `payload` | optional first 01 MongoDB Data Loader | `payload` | 이전 state에 `data_ref`만 있을 때 preview 복원 |
| 5 | optional first 01 MongoDB Data Loader | `payload_out` | 02 Metadata Context Loader | `payload` | optional preview-restored state |
| 6 | Text/Secret Input | value | 02 Metadata Context Loader | `mongo_uri` | MongoDB 사용 시 필요 |
| 7 | Text Input | value | 02 Metadata Context Loader | `mongo_database` | 기본값 예: `metadata_driven_agent_v2` |
| 8 | Text Input 3개 | value | 02 Metadata Context Loader | `domain_collection_name`, `table_catalog_collection_name`, `main_flow_filter_collection_name` | full collection name 입력 |
| 9 | Text Input | value | 18 MongoDB Data Store, 01 MongoDB Data Loader | `result_collection_name` | full collection name 입력. 기본 `agent_v2_result_store` |
| 10 | 02 Metadata Context Loader | `payload_out` | 03 Route Candidate Builder | `payload` | metadata QA 선분기 |
| 10B | 03 Route Candidate Builder | `payload_out` | 04 Route Classifier Prompt Builder | `payload` | route prompt 생성 |
| 10C | 04 Route Classifier Prompt Builder | `route_prompt` | LLM-R Route Classifier LLM | prompt/message input | `route_llm_required=true`일 때만 필요 |
| 10D | 03 Route Candidate Builder | `payload_out` | 05 Route Classifier Normalizer | `payload` | route payload branch |
| 10E | LLM-R Route Classifier LLM | text/message output | 05 Route Classifier Normalizer | `llm_response` | optional route JSON |
| 10F | 05 Route Classifier Normalizer | `payload_out` | 06 Metadata QA Response Builder | `payload` | 직접 답변 또는 pass-through |
| 10G | 06 Metadata QA Response Builder | `payload_out` | 07 Intent Prompt Builder | `payload` | metadata 포함 payload |
| 11 | 07 Intent Prompt Builder | `intent_prompt` | LLM-A Gemini/LLM Intent JSON | prompt/message input | JSON-only 응답 권장 |
| 12 | 06 Metadata QA Response Builder | `payload_out` | 08 Intent Plan Normalizer | `payload` | LLM 응답과 결합할 payload |
| 13 | LLM-A Gemini/LLM Intent JSON | text/message output | 08 Intent Plan Normalizer | `llm_response` | intent JSON 응답 |
| 14 | 08 Intent Plan Normalizer | `payload_out` | 01 MongoDB Data Loader second instance | `payload` | `restore_mode=auto` |
| 15 | second 01 MongoDB Data Loader | `payload_out` | 09~13 retriever node(s) | `payload` | 이전 결과 전체 복원 반영 payload |
| 16 | second 01 MongoDB Data Loader | `payload_out` | 15 Retrieval Payload Adapter | `main_payload` | main payload branch |
| 17 | 14 Source Retrieval Merger | `retrieval_payload` | 15 Retrieval Payload Adapter | `retrieval_payload` | source 조회 결과 병합 |
| 18 | 15 Retrieval Payload Adapter | `payload` | 16 Pandas Prompt Builder | `payload` | pandas prompt 생성 |
| 19 | 16 Pandas Prompt Builder | `pandas_prompt` | LLM-B Gemini/LLM Pandas Code JSON | prompt/message input | JSON-only 응답 필수 |
| 20 | 15 Retrieval Payload Adapter | `payload` | 17 Pandas Code Executor | `payload` | code 실행용 source rows payload |
| 21 | LLM-B Gemini/LLM Pandas Code JSON | text/message output | 17 Pandas Code Executor | `llm_response` | pandas code JSON 응답 |
| 22 | 17 Pandas Code Executor | `payload_out` | 18 MongoDB Data Store | `payload` | source/result rows compact |
| 23 | 18 MongoDB Data Store | `payload_out` | 19 Answer Prompt Builder | `payload` | 최종 답변 prompt 생성 |
| 24 | 19 Answer Prompt Builder | `answer_prompt` | LLM-C Gemini/LLM Final Answer | prompt/message input | plain Korean text 또는 JSON 가능 |
| 25 | 18 MongoDB Data Store | `payload_out` | 20 Answer Response Builder | `payload` | 답변/state 조립용 payload |
| 26 | LLM-C Gemini/LLM Final Answer | text/message output | 20 Answer Response Builder | `llm_response` | 최종 답변 |
| 27 | 20 Answer Response Builder | `payload_out` | 21 Answer Message Adapter | `payload` | Playground 출력용 message 생성 |
| 28 | 21 Answer Message Adapter | `message` | Chat Output | `message` | 사용자에게 보일 최종 출력 |
| 29 | 20 Answer Response Builder | `payload_out.state` | State Store | stored state | 다음 질문의 00 `state` input으로 재사용 |

### 1.3 MongoDB Result Store 입력 의미

| 입력 | 의미 | 운영 기준 |
| --- | --- | --- |
| `mongo_uri` | MongoDB 접속 URI | 비워두면 `MONGODB_URI` 사용 |
| `mongo_database` | database 이름 | 비워두면 `MONGODB_DATABASE` 사용 |
| `result_collection_name` | row payload 저장용 full collection name | 기본 `agent_v2_result_store`, prefix 조합 없음 |
| `enabled` | 저장/조회 사용 여부 | 운영은 `true`, 로컬 단위 테스트는 `false` 가능 |
| `preview_row_limit` | payload에 남길 preview row 수 | 기본 5 |
| `min_rows` | 이 row 수 이상이면 MongoDB에 저장 | 기본 1 |

compact previous state에 preview rows, `row_count`, `columns`, `data_ref`, `product_key_values`가 있으면 첫 번째 `01 MongoDB Data Loader`는 생략할 수 있습니다. 이전 state에 `data_ref`만 있고 preview/summary가 없을 때만 optional first loader를 `preview` 모드로 둡니다. 이전 결과 전체 rows가 필요한 후속 분석에서만 MongoDB Data Loader가 전체 복원을 수행합니다.

## 2. Main Flow Retrieval Nodes

### 2.1 로컬/dummy 검증용 연결

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| D1 | 08 Intent Plan Normalizer | `payload_out` | 09 Dummy Data Retriever | `payload` |
| D2 | 09 Dummy Data Retriever | `retrieval_payload` | 15 Retrieval Payload Adapter | `retrieval_payload` |

`Source Retrieval Merger`는 생략해도 됩니다.

### 2.2 source_type별 운영 연결

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| R1 | 08 Intent Plan Normalizer | `payload_out` | 10 Oracle Query Retriever | `payload` |
| R2 | 08 Intent Plan Normalizer | `payload_out` | 11 H-API Retriever | `payload` |
| R3 | 08 Intent Plan Normalizer | `payload_out` | 12 Datalake Retriever | `payload` |
| R4 | 08 Intent Plan Normalizer | `payload_out` | 13 Goodocs Retriever | `payload` |
| R5 | 10 Oracle Query Retriever | `retrieval_payload` | 14 Source Retrieval Merger | `oracle_retrieval` |
| R6 | 11 H-API Retriever | `retrieval_payload` | 14 Source Retrieval Merger | `h_api_retrieval` |
| R7 | 12 Datalake Retriever | `retrieval_payload` | 14 Source Retrieval Merger | `datalake_retrieval` |
| R8 | 13 Goodocs Retriever | `retrieval_payload` | 14 Source Retrieval Merger | `goodocs_retrieval` |
| R9 | 14 Source Retrieval Merger | `retrieval_payload` | 15 Retrieval Payload Adapter | `retrieval_payload` |

`source_results[]`는 최소한 `dataset_key`, `source_alias`, `source_type`, `data`, `columns`, `row_count`, `applied_params`, `applied_filters`를 맞추는 것이 좋습니다.

## 3. Follow-up State 연결

follow-up 질문을 처리하려면 #26 이후 compact된 payload의 `state`를 다음 turn의 00 `state` input으로 다시 넣습니다.

State에 들어가는 핵심 값:

- `chat_history`
- `context.last_intent_type`
- `context.last_analysis_kind`
- `context.last_source_aliases`
- `current_data.columns`
- `current_data.rows` preview 또는 MongoDB `current_data.data_ref`
- `current_data.source_dataset_keys`
- `current_data.product_key_columns`
- `current_data.product_key_values`
- `followup_source_results`

다음 turn 시작 시 `00 Request State Loader -> 01 MongoDB Data Loader -> 02 Metadata Context Loader` 순서로 연결하면 compact된 `current_data.data_ref`가 기본적으로 preview/summary로 복원됩니다. 후속 “이 제품”류 질문은 `product_key_values`를 우선 사용하므로 초반 full rows restore가 필요하지 않습니다.

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




