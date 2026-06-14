# Main Flow Connection Guide

이 문서는 실제 질의/분석 agent를 Langflow canvas에서 연결하는 기준입니다.
큰 row payload는 MongoDB result store에 저장하고, flow 안에서는 `data_ref`를 들고 다닌 뒤 pandas 실행 전 다시 hydrate합니다.

## Nodes

| # | Node | Component file | Role |
| --- | --- | --- | --- |
| 00 | `00 Request State Loader` | `00_request_state_loader.py` | 질문, session id, 이전 state를 compact payload로 생성 |
| 01 | `01 Metadata Context Loader` | `01_metadata_context_loader.py` | MongoDB에서 domain/table/filter metadata 로드 |
| 02 | `02 Intent Prompt Builder` | `02_intent_prompt_builder.py` | 의도 분석 prompt 생성 |
| LLM-A | Gemini/LLM intent node | Langflow 기본 LLM node | intent JSON 생성 |
| 03 | `03 Intent Plan Normalizer` | `03_intent_plan_normalizer.py` | intent JSON을 retrieval jobs와 route로 정규화 |
| 04 | `04 Retrieval Payload Adapter` | `04_retrieval_payload_adapter.py` | 별도 retrieval flow 결과를 main payload에 병합 |
| 05 | `05 MongoDB Data Store` | `05_mongodb_data_store.py` | `runtime_sources`, `data.rows`, `state.current_data.rows` 같은 큰 row list를 MongoDB에 저장하고 ref로 축약 |
| 06 | `06 MongoDB Data Loader` | `06_mongodb_data_loader.py` | MongoDB `data_ref`를 pandas 실행 또는 후속 질문 전에 rows로 복원 |
| 07 | `07 Pandas Prompt Builder` | `07_pandas_prompt_builder.py` | pandas code JSON 생성용 prompt 생성 |
| LLM-B | Gemini/LLM pandas node | Langflow 기본 LLM node | pandas code JSON 생성 |
| 08 | `08 Pandas Code Executor` | `08_pandas_code_executor.py` | safety check 후 pandas code 실행 |
| 09 | `09 Answer Prompt Builder` | `09_answer_prompt_builder.py` | 최종 답변 prompt 생성 |
| LLM-C | Gemini/LLM answer node | Langflow 기본 LLM node | 최종 한국어 답변 생성 |
| 10 | `10 Answer Response Builder` | `10_answer_response_builder.py` | 답변, data, applied_scope, next state 생성 |
| 11 | `11 Answer Message Adapter` | `11_answer_message_adapter.py` | Playground에 답변/표/의도/pandas 코드를 Markdown으로 표시 |

## Required Connections

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| 1 | `Chat Input` | `message` or `text` | `00 Request State Loader` | `question` |
| 2 | Text input | fixed session id | `00 Request State Loader` | `session_id` |
| 3 | Previous state source | Data | `00 Request State Loader` | `state` |
| 4 | `00 Request State Loader` | `payload` | `06 MongoDB Data Loader` | `payload` |
| 5 | `06 MongoDB Data Loader` | `payload_out` | `01 Metadata Context Loader` | `payload` |
| 6 | Text input | MongoDB URI | `01 Metadata Context Loader`, `05 MongoDB Data Store`, `06 MongoDB Data Loader` | `mongo_uri` |
| 7 | Text input | DB name | `01 Metadata Context Loader`, `05 MongoDB Data Store`, `06 MongoDB Data Loader` | `mongo_database` |
| 8 | Text input 3개 | full metadata collection names | `01 Metadata Context Loader` | `domain_collection_name`, `table_catalog_collection_name`, `main_flow_filter_collection_name` |
| 9 | Text input | result collection full name, e.g. `agent_v2_result_store` | `05 MongoDB Data Store`, `06 MongoDB Data Loader` | `result_collection_name` |
| 10 | `01 Metadata Context Loader` | `payload_out` | `02 Intent Prompt Builder` | `payload` |
| 11 | `02 Intent Prompt Builder` | `intent_prompt` | Gemini/LLM intent node | prompt/message input |
| 12 | `01 Metadata Context Loader` | `payload_out` | `03 Intent Plan Normalizer` | `payload` |
| 13 | Gemini/LLM intent node | text/message output | `03 Intent Plan Normalizer` | `llm_response` |

If the previous state never contains MongoDB refs, connection #4 can be skipped. In production, keep it so follow-up questions can restore compacted `state.current_data`.

## Retrieval Bridge

Dummy 또는 source별 retrieval flow 중 하나를 선택합니다. 자세한 retrieval flow 연결은 `../data_retrieval_flow/CONNECTION_GUIDE.md`를 따릅니다.

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| 14 | `03 Intent Plan Normalizer` | `payload_out` | retrieval flow start node(s) | `payload` |
| 15 | `03 Intent Plan Normalizer` | `payload_out` | `04 Retrieval Payload Adapter` | `main_payload` |
| 16 | retrieval flow end node | `retrieval_payload` | `04 Retrieval Payload Adapter` | `retrieval_payload` |
| 17 | `04 Retrieval Payload Adapter` | `payload` | `05 MongoDB Data Store` | `payload` |
| 18 | `05 MongoDB Data Store` | `payload_out` | `06 MongoDB Data Loader` | `payload` |

At #17, `runtime_sources` is compacted to preview rows plus `runtime_source_refs`. At #18, those refs are restored so pandas receives full DataFrames.

## Pandas And Answer

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| 19 | `06 MongoDB Data Loader` | `payload_out` | `07 Pandas Prompt Builder` | `payload` |
| 20 | `07 Pandas Prompt Builder` | `pandas_prompt` | Gemini/LLM pandas node | prompt/message input |
| 21 | `06 MongoDB Data Loader` | `payload_out` | `08 Pandas Code Executor` | `payload` |
| 22 | Gemini/LLM pandas node | text/message output | `08 Pandas Code Executor` | `llm_response` |
| 23 | `08 Pandas Code Executor` | `payload_out` | `09 Answer Prompt Builder` | `payload` |
| 24 | `09 Answer Prompt Builder` | `answer_prompt` | Gemini/LLM answer node | prompt/message input |
| 25 | `08 Pandas Code Executor` | `payload_out` | `10 Answer Response Builder` | `payload` |
| 26 | Gemini/LLM answer node | text/message output | `10 Answer Response Builder` | `llm_response` |
| 27 | `10 Answer Response Builder` | `payload_out` | `05 MongoDB Data Store` | `payload` |
| 28 | `05 MongoDB Data Store` | `payload_out` | `11 Answer Message Adapter` | `payload` |
| 29 | `11 Answer Message Adapter` | `message` | `Chat Output` | `message` |
| 30 | `05 MongoDB Data Store` after #27 | `payload_out.state` | State Store | stored state |

## MongoDB Result Store Inputs

- `mongo_uri`: MongoDB connection URI. 빈 값이면 `MONGODB_URI` 환경변수를 사용합니다.
- `mongo_database`: database 이름. 빈 값이면 `MONGODB_DATABASE`를 사용합니다.
- `result_collection_name`: result store full collection name. 기본값은 `agent_v2_result_store`이고, 빈 값이면 `MONGODB_RESULT_COLLECTION`을 사용합니다.
- `preview_row_limit`: payload에 남길 preview row 수입니다.
- `min_rows`: 이 row 수 이상이면 MongoDB에 저장합니다.

## Notes

- metadata collection은 prefix 조합이 아니라 `domain_collection_name`, `table_catalog_collection_name`, `main_flow_filter_collection_name`에 full collection name을 직접 입력합니다.
- result row collection도 prefix가 아니라 `result_collection_name` full name을 직접 입력합니다.
- `03 Intent Plan Normalizer`는 LLM이 만든 `retrieval_jobs`를 그대로 통과시키지 않고, MongoDB metadata를 기준으로 필수 params, 날짜 형식, 공정/제품/상태 filter, 후속 질문의 이전 제품 key를 보강합니다. 계산식이나 공정별 특수 로직은 코드 fallback에 넣지 말고 domain/table/filter metadata로 보강해야 합니다.
- `11 Answer Message Adapter`는 최종 payload를 새로 저장하지 않고, 앞 단계에서 이미 compact된 payload를 읽어 Playground용 Markdown만 만듭니다.
