# Main Flow Connection Guide

이 문서는 실제 질의/분석 agent의 Langflow canvas 연결표입니다. 실제 reasoning은 Gemini/LLM 노드가 담당하고, custom component는 prompt 생성, JSON 정규화, retrieval payload 병합, pandas 실행, 최종 응답 정리를 담당합니다.

## Nodes

| # | Node | Component file | Role |
| --- | --- | --- | --- |
| 00 | `00 Request State Loader` | `00_request_state_loader.py` | 사용자 질문, session id, 이전 state를 compact payload로 생성 |
| 01 | `01 Metadata Context Loader` | `01_metadata_context_loader.py` | MongoDB 또는 local JSON에서 domain/table/filter metadata 로드 |
| 02 | `02 Intent Prompt Builder` | `02_intent_prompt_builder.py` | 의도 분석용 prompt 생성 |
| LLM | Gemini/LLM intent node | Langflow 기본 LLM 노드 | intent JSON 생성 |
| 03 | `03 Intent Plan Normalizer` | `03_intent_plan_normalizer.py` | intent JSON을 retrieval jobs와 route로 정규화 |
| 04 | `04 Retrieval Payload Adapter` | `04_retrieval_payload_adapter.py` | 별도 retrieval flow 결과를 main payload에 병합 |
| 05 | `05 Pandas Prompt Builder` | `05_pandas_prompt_builder.py` | pandas code JSON 생성용 prompt 생성 |
| LLM | Gemini/LLM pandas node | Langflow 기본 LLM 노드 | pandas code JSON 생성 |
| 06 | `06 Pandas Code Executor` | `06_pandas_code_executor.py` | safety check 후 pandas code 실행 |
| 07 | `07 Answer Prompt Builder` | `07_answer_prompt_builder.py` | 최종 답변 prompt 생성 |
| LLM | Gemini/LLM answer node | Langflow 기본 LLM 노드 | 최종 한국어 답변 생성 |
| 08 | `08 Answer Response Builder` | `08_answer_response_builder.py` | 답변, data, applied_scope, next state 생성 |
| 09 | `09 Answer Message Adapter` | `09_answer_message_adapter.py` | Playground에 답변/표/의도/pandas 코드를 Markdown으로 표시 |

## Required Connections

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| 1 | `Chat Input` | `message` or `text` | `00 Request State Loader` | `question` |
| 2 | Text input | fixed session id | `00 Request State Loader` | `session_id` |
| 3 | Previous state source | Data | `00 Request State Loader` | `state` |
| 4 | `00 Request State Loader` | `payload` | `01 Metadata Context Loader` | `payload` |
| 5 | Text input | MongoDB URI | `01 Metadata Context Loader` | `mongo_uri` |
| 6 | Text input | DB name | `01 Metadata Context Loader` | `mongo_database` |
| 7 | Text input 3개 | full metadata collection names | `01 Metadata Context Loader` | `domain_collection_name`, `table_catalog_collection_name`, `main_flow_filter_collection_name` |
| 8 | `01 Metadata Context Loader` | `payload_out` | `02 Intent Prompt Builder` | `payload` |
| 9 | `02 Intent Prompt Builder` | `intent_prompt` | Gemini/LLM intent node | prompt/message input |
| 10 | `01 Metadata Context Loader` | `payload_out` | `03 Intent Plan Normalizer` | `payload` |
| 11 | Gemini/LLM intent node | text/message output | `03 Intent Plan Normalizer` | `llm_response` |

## Retrieval Bridge

Dummy 또는 실제 source별 retrieval flow 중 하나를 선택합니다. 자세한 retrieval flow 내부 연결은 `../data_retrieval_flow/CONNECTION_GUIDE.md`를 보세요.

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| 12 | `03 Intent Plan Normalizer` | `payload_out` | retrieval flow start node(s) | `payload` |
| 13 | `03 Intent Plan Normalizer` | `payload_out` | `04 Retrieval Payload Adapter` | `main_payload` |
| 14 | retrieval flow end node | `retrieval_payload` | `04 Retrieval Payload Adapter` | `retrieval_payload` |

## Pandas And Answer

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| 15 | `04 Retrieval Payload Adapter` | `payload` | `05 Pandas Prompt Builder` | `payload` |
| 16 | `05 Pandas Prompt Builder` | `pandas_prompt` | Gemini/LLM pandas node | prompt/message input |
| 17 | `04 Retrieval Payload Adapter` | `payload` | `06 Pandas Code Executor` | `payload` |
| 18 | Gemini/LLM pandas node | text/message output | `06 Pandas Code Executor` | `llm_response` |
| 19 | `06 Pandas Code Executor` | `payload_out` | `07 Answer Prompt Builder` | `payload` |
| 20 | `07 Answer Prompt Builder` | `answer_prompt` | Gemini/LLM answer node | prompt/message input |
| 21 | `06 Pandas Code Executor` | `payload_out` | `08 Answer Response Builder` | `payload` |
| 22 | Gemini/LLM answer node | text/message output | `08 Answer Response Builder` | `llm_response` |
| 23 | `08 Answer Response Builder` | `payload_out` | `09 Answer Message Adapter` | `payload` |
| 24 | `09 Answer Message Adapter` | `message` | `Chat Output` | `message` |

## Notes

- Gemini/LLM 노드는 JSON-only 응답을 권장합니다.
- `09 Answer Message Adapter`는 별도 payload branch를 만들지 않고, 최종 payload를 읽어 Playground에 답변, 결과표, 의도 분석, retrieval plan, pandas code를 같이 보여줍니다.
- 운영에서는 `data_ref`가 `memory://...` trace가 아니라 MongoDB/cache 저장 key가 되도록 별도 저장소를 붙이는 것이 좋습니다.
