# Main Flow Connection Guide

이 문서는 현재 `langflow_components/main_flow` 파일 기준 Langflow canvas 연결 가이드입니다.

핵심 흐름은 다음과 같습니다.

- 앞단 `01 MongoDB Data Loader`는 이전 turn의 `state.current_data.data_ref`를 기본 `preview` 모드로 가볍게 복원합니다.
- 후속 질문이 이전 결과 rows 전체를 다시 분석해야 하면 `04 Intent Plan Normalizer`가 `intent_plan.requires_full_state_hydrate=true`와 `state_hydrate_mode=full`을 설정합니다.
- `04` 뒤에 같은 `01 MongoDB Data Loader` 컴포넌트를 두 번째 인스턴스로 배치하고, 이 인스턴스만 `hydrate_mode=auto`로 둡니다. 평소에는 preview로 통과하고, 위 플래그가 있을 때만 full hydrate합니다.
- `08 MongoDB Data Store`는 `07 Pandas Code Executor` 직후에 연결합니다. 여기서 원본 `runtime_sources`와 pandas 결과 `analysis.rows`를 모두 MongoDB에 저장하고 payload에는 preview rows와 `data_ref`만 남깁니다.
- `10 Answer Response Builder`는 `analysis.data_ref`를 최종 `data.data_ref`와 `state.current_data.data_ref`로 이어받습니다.

## Node Inventory

| # | Node | Component file | Required inputs | Outputs |
| --- | --- | --- | --- | --- |
| 00 | `00 Request State Loader` | `00_request_state_loader.py` | `question`, `session_id`, optional `state` | `payload` |
| 01 | `01 MongoDB Data Loader` | `01_mongodb_data_loader.py` | `payload` | `payload_out` |
| 02 | `02 Metadata Context Loader` | `02_metadata_context_loader.py` | `payload` | `payload_out` |
| 03 | `03 Intent Prompt Builder` | `03_intent_prompt_builder.py` | `payload` | `intent_prompt`, `prompt_payload` |
| LLM-A | Intent LLM | Langflow LLM node | prompt/message | text/message |
| 04 | `04 Intent Plan Normalizer` | `04_intent_plan_normalizer.py` | `payload`, `llm_response` | `payload_out` |
| 04B | `01 MongoDB Data Loader` second instance | `01_mongodb_data_loader.py` | `payload` | `payload_out` |
| Retrieval | Data Retrieval Flow | `../data_retrieval_flow` | `payload` | `retrieval_payload` |
| 05 | `05 Retrieval Payload Adapter` | `05_retrieval_payload_adapter.py` | `main_payload`, `retrieval_payload` | `payload` |
| 06 | `06 Pandas Prompt Builder` | `06_pandas_prompt_builder.py` | `payload` | `pandas_prompt`, `prompt_payload` |
| LLM-B | Pandas Code LLM | Langflow LLM node | prompt/message | text/message |
| 07 | `07 Pandas Code Executor` | `07_pandas_code_executor.py` | `payload`, `llm_response` | `payload_out` |
| 08 | `08 MongoDB Data Store` | `08_mongodb_data_store.py` | `payload` | `payload_out` |
| 09 | `09 Answer Prompt Builder` | `09_answer_prompt_builder.py` | `payload` | `answer_prompt`, `prompt_payload` |
| LLM-C | Answer LLM | Langflow LLM node | prompt/message | text/message |
| 10 | `10 Answer Response Builder` | `10_answer_response_builder.py` | `payload`, `llm_response` | `payload_out` |
| 11 | `11 Answer Message Adapter` | `11_answer_message_adapter.py` | `payload` | `message` |

## Required Main Spine

| # | From node | From output | To node | To input | Note |
| --- | --- | --- | --- | --- | --- |
| 1 | `Chat Input` | `message` or `text` | `00 Request State Loader` | `question` | 사용자 질문 |
| 2 | Text/Input field | value | `00 Request State Loader` | `session_id` | 사용자/session key |
| 3 | Previous state source | Data | `00 Request State Loader` | `state` | 후속 질문이면 연결 |
| 4 | `00 Request State Loader` | `payload` | `01 MongoDB Data Loader` | `payload` | 이전 `data_ref` preview/summary 복원 |
| 5 | `01 MongoDB Data Loader` | `payload_out` | `02 Metadata Context Loader` | `payload` | metadata 추가 |
| 6 | `02 Metadata Context Loader` | `payload_out` | `03 Intent Prompt Builder` | `payload` | intent prompt 생성 |
| 7 | `03 Intent Prompt Builder` | `intent_prompt` | Intent LLM | prompt/message input | JSON intent 생성 |
| 8 | `02 Metadata Context Loader` | `payload_out` | `04 Intent Plan Normalizer` | `payload` | 원 payload |
| 9 | Intent LLM | text/message output | `04 Intent Plan Normalizer` | `llm_response` | intent JSON 응답 |
| 10 | `04 Intent Plan Normalizer` | `payload_out` | `01 MongoDB Data Loader` second instance | `payload` | `hydrate_mode=auto` |
| 11 | second `01 MongoDB Data Loader` | `payload_out` | Retrieval flow start node(s) | `payload` | full hydrate 반영 payload |
| 12 | second `01 MongoDB Data Loader` | `payload_out` | `05 Retrieval Payload Adapter` | `main_payload` | main payload branch |
| 13 | Retrieval flow end node | `retrieval_payload` | `05 Retrieval Payload Adapter` | `retrieval_payload` | source rows 병합 |
| 14 | `05 Retrieval Payload Adapter` | `payload` | `06 Pandas Prompt Builder` | `payload` | source rows 포함 payload |
| 15 | `06 Pandas Prompt Builder` | `pandas_prompt` | Pandas Code LLM | prompt/message input | JSON-only pandas code |
| 16 | `05 Retrieval Payload Adapter` | `payload` | `07 Pandas Code Executor` | `payload` | LLM code와 합칠 payload |
| 17 | Pandas Code LLM | text/message output | `07 Pandas Code Executor` | `llm_response` | pandas code JSON |
| 18 | `07 Pandas Code Executor` | `payload_out` | `08 MongoDB Data Store` | `payload` | source/result rows 저장 및 compact |
| 19 | `08 MongoDB Data Store` | `payload_out` | `09 Answer Prompt Builder` | `payload` | compacted result preview로 답변 prompt 생성 |
| 20 | `09 Answer Prompt Builder` | `answer_prompt` | Answer LLM | prompt/message input | 한국어 답변 생성 |
| 21 | `08 MongoDB Data Store` | `payload_out` | `10 Answer Response Builder` | `payload` | 저장된 `analysis.data_ref` 포함 payload |
| 22 | Answer LLM | text/message output | `10 Answer Response Builder` | `llm_response` | 최종 답변 |
| 23 | `10 Answer Response Builder` | `payload_out` | `11 Answer Message Adapter` | `payload` | Playground Markdown 생성 |
| 24 | `11 Answer Message Adapter` | `message` | `Chat Output` | `message` | 사용자 표시 |
| 25 | `10 Answer Response Builder` | `payload_out.state` | State Store/Web backend | stored state | 다음 turn의 `00.state`로 재사용 |

## MongoDB Config Inputs

| Target node | Input | Recommended value |
| --- | --- | --- |
| first `01 MongoDB Data Loader` | `mongo_uri` | 비워두면 `MONGODB_URI` |
| first `01 MongoDB Data Loader` | `mongo_database` | 비워두면 `MONGODB_DATABASE` |
| first `01 MongoDB Data Loader` | `result_collection_name` | `agent_v2_result_store` 또는 `MONGODB_RESULT_COLLECTION` |
| first `01 MongoDB Data Loader` | `hydrate_mode` | `preview` |
| first `01 MongoDB Data Loader` | `preview_row_limit` | 기본 `5` |
| second `01 MongoDB Data Loader` | `hydrate_mode` | `auto` |
| second `01 MongoDB Data Loader` | `preview_row_limit` | 기본 `5` |
| `02 Metadata Context Loader` | `mongo_uri` | MongoDB metadata 조회 URI |
| `02 Metadata Context Loader` | `mongo_database` | `metadata_driven_agent_v2` 또는 운영 DB |
| `02 Metadata Context Loader` | `domain_collection_name` | `agent_v2_domain_items` |
| `02 Metadata Context Loader` | `table_catalog_collection_name` | `agent_v2_table_catalog_items` |
| `02 Metadata Context Loader` | `main_flow_filter_collection_name` | `agent_v2_main_flow_filters` |
| `08 MongoDB Data Store` | `mongo_uri` | 비워두면 `MONGODB_URI` |
| `08 MongoDB Data Store` | `mongo_database` | 비워두면 `MONGODB_DATABASE` |
| `08 MongoDB Data Store` | `result_collection_name` | `agent_v2_result_store` 또는 `MONGODB_RESULT_COLLECTION` |
| `08 MongoDB Data Store` | `enabled` | 기본 `true` |
| `08 MongoDB Data Store` | `preview_row_limit` | 기본 `5` |
| `08 MongoDB Data Store` | `min_rows` | 기본 `1` |

Metadata collection과 result store collection은 prefix 조합이 아니라 full collection name을 직접 입력합니다.

## Minimal Canvas Sequence

```text
Chat Input
-> 00 Request State Loader
-> 01 MongoDB Data Loader (preview)
-> 02 Metadata Context Loader
-> 03 Intent Prompt Builder
-> Intent LLM
-> 04 Intent Plan Normalizer
-> 01 MongoDB Data Loader (second instance, hydrate_mode=auto)
-> Data Retrieval Flow
-> 05 Retrieval Payload Adapter
-> 06 Pandas Prompt Builder
-> Pandas Code LLM
-> 07 Pandas Code Executor
-> 08 MongoDB Data Store
-> 09 Answer Prompt Builder
-> Answer LLM
-> 10 Answer Response Builder
-> 11 Answer Message Adapter
-> Chat Output
```

병렬 payload branch는 다음을 지켜야 합니다.

```text
02 Metadata Context Loader.payload_out -> 04 Intent Plan Normalizer.payload
04 Intent Plan Normalizer.payload_out -> second 01 MongoDB Data Loader.payload
second 01 MongoDB Data Loader.payload_out -> 05 Retrieval Payload Adapter.main_payload
05 Retrieval Payload Adapter.payload -> 07 Pandas Code Executor.payload
08 MongoDB Data Store.payload_out -> 10 Answer Response Builder.payload
10 Answer Response Builder.payload_out.state -> next turn state store
```

## Stored Data Contract

`08 MongoDB Data Store`는 pandas 직후 payload에서 다음 row list를 저장합니다.

- `runtime_sources.<source_alias>`: 분석에 사용된 원본 retrieval rows
- `analysis.rows`: pandas executor가 만든 최종 결과 rows

저장 뒤 payload에는 preview rows, `row_count`, `columns`, `data_ref`가 남습니다. `10 Answer Response Builder`는 `analysis.data_ref`를 `data.data_ref`와 `state.current_data.data_ref`로 이어받으므로, 다음 turn state에는 전체 rows가 아니라 compact reference와 summary만 저장됩니다.

## Full Hydrate Policy

기본 후속 질문은 `state.current_data.product_key_values`, `row_count`, `columns`, preview rows만 사용합니다.

다음 유형은 이전 결과 rows 전체가 필요하므로 `04 Intent Plan Normalizer`가 full hydrate를 요청합니다.

- 이전 결과 전체/상세/원본 rows를 다시 보여 달라는 질문
- 이전 결과를 다시 정렬, 필터, top/bottom, groupby, 합계/평균 등으로 재분석하는 질문
- LLM intent JSON이 `requires_full_state_hydrate=true` 또는 `state_hydrate_mode=full`을 명시한 경우

반대로 “이 제품/해당 제품의 장비를 보여줘”처럼 이전 결과의 제품 key만 새 retrieval에 쓰는 질문은 summary hydrate로 충분합니다.

## Do Not Connect This Way

- 같은 turn에서 `05 Retrieval Payload Adapter -> 08 MongoDB Data Store -> 01 MongoDB Data Loader -> 06 Pandas Prompt Builder`로 source rows를 저장했다가 재로드하지 않습니다. 같은 turn 분석은 `runtime_sources`를 직접 사용합니다.
- `09 Answer Prompt Builder.prompt_payload`를 normalizer/executor의 `payload`로 연결하지 않습니다. 이 output은 prompt 디버깅용 Data입니다.
- `11 Answer Message Adapter.message`를 후속 state로 저장하지 않습니다. 후속 state는 `10 Answer Response Builder.payload_out.state`를 사용합니다.
