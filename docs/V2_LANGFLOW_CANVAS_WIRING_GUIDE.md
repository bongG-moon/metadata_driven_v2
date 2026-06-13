# V2 Langflow Canvas Wiring Guide

이 문서는 `metadata_driven_v2`를 base flow로 사용할 때 Langflow canvas에서 어떤 node의 output을 어떤 node의 input에 연결해야 하는지 정리한 구현용 연결표다.

핵심 원칙:

- 실제 reasoning은 Langflow의 Gemini/LLM node가 담당한다.
- custom component는 prompt 생성, LLM 응답 정규화, retrieval payload 병합, pandas code 실행, state 생성, 응답 표시를 담당한다.
- numbered component 파일은 Langflow custom component에 하나씩 붙여 넣어도 동작하도록 standalone으로 작성되어 있다.
- `prompt_payload` output은 디버깅용이다. 운영 canvas의 필수 연결은 보통 `*_prompt`, `payload`, `payload_out`, `retrieval_payload`, `message`만 사용한다.

## 1. Main Query/Analysis Flow

### 1.1 Node 목록

| 순서 | Langflow node 이름 | Component file | 주요 역할 |
| --- | --- | --- | --- |
| Input | Chat Input | Langflow 기본 node | 사용자 질문 입력 |
| 00 | 00 Request State Loader | `langflow_components/main_flow/00_request_state_loader.py` | 질문, session id, 이전 state를 compact payload로 변환 |
| 01 | 01 Metadata Context Loader | `langflow_components/main_flow/01_metadata_context_loader.py` | MongoDB 또는 local JSON metadata 로드 |
| 02 | 02 Intent Prompt Builder | `langflow_components/main_flow/02_intent_prompt_builder.py` | intent JSON 생성을 위한 LLM prompt 생성 |
| LLM-A | Gemini/LLM Intent JSON | Langflow 기본 Gemini/LLM node | intent JSON 생성 |
| 03 | 03 Intent Plan Normalizer | `langflow_components/main_flow/03_intent_plan_normalizer.py` | intent JSON 정규화, retrieval_jobs 생성/보강 |
| Retrieval | Data Retrieval Flow | 아래 2장 참고 | source_type별 데이터 조회 |
| 04 | 04 Retrieval Payload Adapter | `langflow_components/main_flow/04_retrieval_payload_adapter.py` | retrieval 결과를 `runtime_sources`로 변환 |
| 05 | 05 Pandas Prompt Builder | `langflow_components/main_flow/05_pandas_prompt_builder.py` | pandas code JSON 생성을 위한 LLM prompt 생성 |
| LLM-B | Gemini/LLM Pandas Code JSON | Langflow 기본 Gemini/LLM node | pandas code JSON 생성 |
| 06 | 06 Pandas Code Executor | `langflow_components/main_flow/06_pandas_code_executor.py` | safety check 후 pandas code 실행 |
| 07 | 07 Answer Prompt Builder | `langflow_components/main_flow/07_answer_prompt_builder.py` | 최종 한국어 답변 생성을 위한 LLM prompt 생성 |
| LLM-C | Gemini/LLM Final Answer | Langflow 기본 Gemini/LLM node | 최종 답변 생성 |
| 08 | 08 Answer Response Builder | `langflow_components/main_flow/08_answer_response_builder.py` | answer, data, applied_scope, next state 조립 |
| 09 | 09 Answer Message Adapter | `langflow_components/main_flow/09_answer_message_adapter.py` | Playground 출력용 Markdown message 생성 |
| Output | Chat Output | Langflow 기본 node | 최종 답변 출력 |

### 1.2 필수 연결표

| # | From node | From output | To node | To input | 설명 |
| --- | --- | --- | --- | --- | --- |
| 1 | Chat Input | `message` 또는 `text` | 00 Request State Loader | `question` | 사용자 질문 |
| 2 | Text Input | value | 00 Request State Loader | `session_id` | 예: `demo-session`, 사용자별 session key 권장 |
| 3 | State Store 또는 이전 08 output | `state` data | 00 Request State Loader | `state` | 선택. follow-up을 쓰려면 필요 |
| 4 | 00 Request State Loader | `payload` | 01 Metadata Context Loader | `payload` | 질문 payload 전달 |
| 5 | Text Input 또는 Secret | value | 01 Metadata Context Loader | `mongo_uri` | MongoDB 사용 시 필요 |
| 6 | Text Input | value | 01 Metadata Context Loader | `mongo_database` | 기본값 예: `metadata_driven_agent_v2` |
| 7 | Text Input 3개 | value | 01 Metadata Context Loader | `domain_collection_name`, `table_catalog_collection_name`, `main_flow_filter_collection_name` | full collection name 입력. 기본값 예: `agent_v2_domain_items`, `agent_v2_table_catalog_items`, `agent_v2_main_flow_filters` |
| 8 | Text Input | value | 01 Metadata Context Loader | `metadata_source` | `mongodb`, `local`, `auto` 중 선택 |
| 9 | Text Input | value | 01 Metadata Context Loader | `metadata_dir` | local 검증 시 `metadata` 폴더 경로 |
| 10 | 01 Metadata Context Loader | `payload_out` | 02 Intent Prompt Builder | `payload` | metadata 포함 payload |
| 11 | 02 Intent Prompt Builder | `intent_prompt` | LLM-A Gemini/LLM Intent JSON | prompt/message input | LLM-A는 JSON-only 응답 권장 |
| 12 | 01 Metadata Context Loader | `payload_out` | 03 Intent Plan Normalizer | `payload` | LLM 응답과 원 payload를 합치기 위해 필요 |
| 13 | LLM-A Gemini/LLM Intent JSON | text/message output | 03 Intent Plan Normalizer | `llm_response` | intent JSON 응답 |
| 14 | 03 Intent Plan Normalizer | `payload_out` | Data Retrieval Flow start node(s) | `payload` | 아래 2장 중 하나 선택 |
| 15 | 03 Intent Plan Normalizer | `payload_out` | 04 Retrieval Payload Adapter | `main_payload` | main payload branch |
| 16 | Data Retrieval Flow end | `retrieval_payload` | 04 Retrieval Payload Adapter | `retrieval_payload` | source 조회 결과 병합 |
| 17 | 04 Retrieval Payload Adapter | `payload` | 05 Pandas Prompt Builder | `payload` | pandas prompt 생성 |
| 18 | 05 Pandas Prompt Builder | `pandas_prompt` | LLM-B Gemini/LLM Pandas Code JSON | prompt/message input | LLM-B는 JSON-only 응답 필수 |
| 19 | 04 Retrieval Payload Adapter | `payload` | 06 Pandas Code Executor | `payload` | code 실행용 source payload |
| 20 | LLM-B Gemini/LLM Pandas Code JSON | text/message output | 06 Pandas Code Executor | `llm_response` | pandas code JSON 응답 |
| 21 | 06 Pandas Code Executor | `payload_out` | 07 Answer Prompt Builder | `payload` | 최종 답변 prompt 생성 |
| 22 | 07 Answer Prompt Builder | `answer_prompt` | LLM-C Gemini/LLM Final Answer | prompt/message input | plain Korean text 또는 JSON 가능 |
| 23 | 06 Pandas Code Executor | `payload_out` | 08 Answer Response Builder | `payload` | 답변/state 조립용 payload |
| 24 | LLM-C Gemini/LLM Final Answer | text/message output | 08 Answer Response Builder | `llm_response` | 최종 답변 |
| 25 | 08 Answer Response Builder | `payload_out` | 09 Answer Message Adapter | `payload` | Playground 출력용 message 생성 |
| 26 | 09 Answer Message Adapter | `message` | Chat Output | `message` | 사용자에게 보일 최종 출력 |
| 27 | 08 Answer Response Builder | `payload_out.state` | State Store | stored state | 다음 질문의 00 `state` input으로 재사용 |

### 1.3 LLM node 설정 권장

LLM-A Intent JSON:

- temperature 낮게 설정 권장
- JSON object만 반환하도록 system/prompt 설정
- `intent_type`, `analysis_kind`, `datasets`, `retrieval_jobs`, `step_plan`, `params_by_dataset`, `filters`를 포함하도록 설정
- v2 보강 후에는 LLM이 `retrieval_jobs`를 누락해도 03이 fallback job을 생성하지만, 운영 품질을 위해 LLM이 직접 내는 것이 좋다.

LLM-B Pandas Code JSON:

- JSON object만 반환
- schema:

```json
{
  "code": "Python pandas code. Must assign result_df.",
  "output_columns": ["expected result columns"],
  "reasoning_steps": ["short steps"]
}
```

- import, file/network access, `eval`, `exec`, `open`, `subprocess`, `np` 사용 금지
- v2 보강 후 06 executor가 `PRODUCTION_sum`, `rank`, 한국어 measure label 등을 표준 컬럼명으로 보정한다.

LLM-C Final Answer:

- 한국어 답변 권장
- JSON으로 줄 경우 `{"answer_message": "..."}` 형태 권장
- plain text도 08에서 처리 가능

## 2. Data Retrieval Flow

Retrieval은 운영 방식에 따라 두 가지로 연결한다.

### 2.1 로컬/dummy 검증용 간단 연결

빠르게 Langflow main flow를 검증할 때는 dummy retriever 하나만 연결한다.

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| D1 | 03 Intent Plan Normalizer | `payload_out` | 01 Dummy Data Retriever | `payload` |
| D2 | 01 Dummy Data Retriever | `retrieval_payload` | 04 Retrieval Payload Adapter | `retrieval_payload` |

이 경우 main flow 연결표의 #14는 `03 -> 01 Dummy`, #16은 `01 Dummy -> 04`가 된다. `Source Retrieval Merger`는 생략해도 된다.

### 2.2 source_type별 운영 연결

Oracle, H-API, Datalake, Goodocs를 source boundary로 분리하려면 아래처럼 연결한다.

| # | From node | From output | To node | To input | 설명 |
| --- | --- | --- | --- | --- | --- |
| R1 | 03 Intent Plan Normalizer | `payload_out` | 02 Oracle Query Retriever | `payload` | `source_type=oracle` job만 처리 |
| R2 | 03 Intent Plan Normalizer | `payload_out` | 03 H-API Retriever | `payload` | `source_type=h_api` job만 처리 |
| R3 | 03 Intent Plan Normalizer | `payload_out` | 04 Datalake Retriever | `payload` | `source_type=datalake` job만 처리 |
| R4 | 03 Intent Plan Normalizer | `payload_out` | 05 Goodocs Retriever | `payload` | `source_type=goodocs` job만 처리 |
| R5 | Secret/Text Input | value | 02 Oracle Query Retriever | `oracle_config` | Oracle 설정 또는 기존 Oracle component bridge |
| R6 | Text Input | value | 02 Oracle Query Retriever | `fetch_limit` | 기본 `5000` |
| R7 | Secret/Text Input | value | 03 H-API Retriever | `api_token` | H-API token |
| R8 | Text Input | value | 03 H-API Retriever | `fetch_limit` | 기본 `5000` |
| R9 | Text Input | value | 04 Datalake Retriever | `lake_user_id` | Datalake user |
| R10 | Secret/Text Input | value | 04 Datalake Retriever | `lake_jwt_token` | Datalake JWT |
| R11 | Text Input | value | 04 Datalake Retriever | `fetch_limit` | 기본 `5000` |
| R12 | Text Input | value | 05 Goodocs Retriever | `goodocs_user_id` | Goodocs user |
| R13 | Secret/Text Input | value | 05 Goodocs Retriever | `goodocs_token` | Goodocs token |
| R14 | Text Input | value | 05 Goodocs Retriever | `fetch_limit` | 기본 `5000` |
| R15 | 02 Oracle Query Retriever | `retrieval_payload` | 06 Source Retrieval Merger | `oracle_retrieval` | Oracle 결과 |
| R16 | 03 H-API Retriever | `retrieval_payload` | 06 Source Retrieval Merger | `h_api_retrieval` | H-API 결과 |
| R17 | 04 Datalake Retriever | `retrieval_payload` | 06 Source Retrieval Merger | `datalake_retrieval` | Datalake 결과 |
| R18 | 05 Goodocs Retriever | `retrieval_payload` | 06 Source Retrieval Merger | `goodocs_retrieval` | Goodocs 결과 |
| R19 | 06 Source Retrieval Merger | `retrieval_payload` | 04 Retrieval Payload Adapter | `retrieval_payload` | main flow로 병합 결과 전달 |

운영 주의:

- 현재 component는 source boundary와 dummy fallback 검증에 초점이 있다.
- 실제 운영 Oracle/H-API/Datalake/Goodocs 호출은 기존 사내 Langflow component 또는 live connector를 이 위치에 꽂는 방식이 적합하다.
- source component output은 반드시 `retrieval_payload.source_results[]` 구조를 맞춰야 한다.

필수 `source_results` item shape:

```json
{
  "success": true,
  "dataset_key": "wip_today",
  "source_alias": "wip_total",
  "source_type": "oracle",
  "data": [{"WORK_DT": "20260612", "WIP": 100}],
  "columns": ["WORK_DT", "WIP"],
  "row_count": 1,
  "applied_params": {"DATE": "20260612"},
  "applied_filters": [{"field": "DATE", "op": "eq", "value": "20260612"}],
  "used_dummy_data": false,
  "source_execution": {}
}
```

## 3. Follow-up State 연결

follow-up 질문을 처리하려면 08 output의 `state`를 다음 턴 00 input으로 되돌려야 한다.

권장 방식:

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| S1 | 08 Answer Response Builder | `payload_out` | State extractor/custom memory | payload |
| S2 | State extractor/custom memory | `state` | 00 Request State Loader | `state` |

State에 들어가는 주요 값:

- `chat_history`: 최근 대화
- `context.last_intent_type`
- `context.last_analysis_kind`
- `context.last_source_aliases`
- `current_data.columns`
- `current_data.rows`
- `current_data.source_dataset_keys`
- `followup_source_results`

후속 질문 예:

1. "현재 da에서 재공이 가장 많은 제품 알려줘"
2. "이 제품에 할당된 장비 현황 알려줘"

두 번째 질문에서 00의 `state` input에 첫 번째 08의 state가 들어가야 `equipment_for_previous_products`가 정상 작동한다.

## 4. Metadata Authoring Flow 공통 연결

아래 세 flow는 같은 연결 패턴을 쓴다.

- Domain: `langflow_components/domain_authoring_flow/`
- Table catalog: `langflow_components/table_catalog_authoring_flow/`
- Main flow filter: `langflow_components/main_flow_filters_authoring_flow/`

### 4.1 Authoring node 역할

| 순서 | 역할 | Domain node | Table node | Filter node |
| --- | --- | --- | --- | --- |
| 00 | 자연어 요청 + Mongo 설정 로드 | 00 Domain Authoring Request Loader | 00 Table Catalog Authoring Request Loader | 00 Main Flow Filter Authoring Request Loader |
| 01 | 정제 prompt 생성 | 01 Domain Text Refinement Prompt Builder | 01 Table Catalog Text Refinement Prompt Builder | 01 Main Flow Filter Text Refinement Prompt Builder |
| LLM-1 | 자연어 정제 | Gemini/LLM refinement | Gemini/LLM refinement | Gemini/LLM refinement |
| 02 | 정제 결과 반영 | 02 Domain Text Refinement Normalizer | 02 Table Catalog Text Refinement Normalizer | 02 Main Flow Filter Text Refinement Normalizer |
| 03 | 저장 후보 JSON prompt 생성 | 03 Domain Authoring Prompt Builder | 03 Table Catalog Authoring Prompt Builder | 03 Main Flow Filter Authoring Prompt Builder |
| LLM-2 | 저장 후보 JSON 생성 | Gemini/LLM authoring JSON | Gemini/LLM authoring JSON | Gemini/LLM authoring JSON |
| 04 | 저장 후보 JSON 정규화 | 04 Domain Authoring Result Normalizer | 04 Table Catalog Authoring Result Normalizer | 04 Main Flow Filter Authoring Result Normalizer |
| 05 | 중복/유사도 점검 | 05 Domain Similarity Checker | 05 Table Catalog Similarity Checker | 05 Main Flow Filter Similarity Checker |
| 06 | 저장 전 review prompt 생성 | 06 Domain Review Prompt Builder | 06 Table Catalog Review Prompt Builder | 06 Main Flow Filter Review Prompt Builder |
| LLM-3 | 저장 가능 여부 review | Gemini/LLM review JSON | Gemini/LLM review JSON | Gemini/LLM review JSON |
| 07 | MongoDB writer | 07 Domain Review Writer | 07 Table Catalog Review Writer | 07 Main Flow Filter Review Writer |
| 08 | 최종 응답 | 08 Domain Authoring Response Builder | 08 Table Catalog Authoring Response Builder | 08 Main Flow Filter Authoring Response Builder |

### 4.2 Authoring 필수 연결표

`XX`는 Domain/Table/Filter 중 하나로 읽으면 된다.

| # | From node | From output | To node | To input | 설명 |
| --- | --- | --- | --- | --- | --- |
| A1 | Chat Input 또는 Text Input | text/message | 00 XX Authoring Request Loader | `raw_text` | 자연어 metadata 설명 |
| A2 | Text/Secret Input | value | 00 XX Authoring Request Loader | `mongo_uri` | MongoDB URI |
| A3 | Text Input | value | 00 XX Authoring Request Loader | `mongo_database` | 기본 `metadata_driven_agent_v2` |
| A4 | Text Input | value | 00 XX Authoring Request Loader | `collection_name` | full collection name 입력. Domain `agent_v2_domain_items`, Table `agent_v2_table_catalog_items`, Filter `agent_v2_main_flow_filters` |
| A6 | Text Input | value | 00 XX Authoring Request Loader | `duplicate_action` | 기본 `ask`; `merge`, `replace`, `skip`, `create_new` 가능 |
| A7 | Text Input | value | 00 XX Authoring Request Loader | `load_existing` | 기본 `true` |
| A8 | Text Input | value | 00 XX Authoring Request Loader | `load_limit` | 기본 `200` |
| A9 | 00 XX Authoring Request Loader | `payload_out` | 01 XX Text Refinement Prompt Builder | `payload` | 정제 prompt 생성 |
| A10 | 01 XX Text Refinement Prompt Builder | `refinement_prompt` | LLM-1 Refinement | prompt/message input | 자연어 정제 |
| A11 | 00 XX Authoring Request Loader | `payload_out` | 02 XX Text Refinement Normalizer | `payload` | 원 payload branch |
| A12 | LLM-1 Refinement | text/message output | 02 XX Text Refinement Normalizer | `llm_response` | 정제 LLM 응답 |
| A13 | 02 XX Text Refinement Normalizer | `payload_out` | 03 XX Authoring Prompt Builder | `payload` | 저장 후보 JSON prompt 생성 |
| A14 | 03 XX Authoring Prompt Builder | `authoring_prompt` | LLM-2 Authoring JSON | prompt/message input | 저장 후보 JSON 생성 |
| A15 | 02 XX Text Refinement Normalizer | `payload_out` | 04 XX Authoring Result Normalizer | `payload` | 정규화용 payload |
| A16 | LLM-2 Authoring JSON | text/message output | 04 XX Authoring Result Normalizer | `llm_response` | 저장 후보 JSON |
| A17 | 04 XX Authoring Result Normalizer | `payload_out` | 05 XX Similarity Checker | `payload` | 중복/유사도 점검 |
| A18 | Text Input | value | 05 XX Similarity Checker | `duplicate_action` | 선택. 00 값 override |
| A19 | 05 XX Similarity Checker | `payload_out` | 06 XX Review Prompt Builder | `payload` | 저장 전 review prompt 생성 |
| A20 | 06 XX Review Prompt Builder | `review_prompt` | LLM-3 Review JSON | prompt/message input | 저장 가능 여부 검토 |
| A21 | 05 XX Similarity Checker | `payload_out` | 07 XX Review Writer | `payload` | writer payload |
| A22 | LLM-3 Review JSON | text/message output | 07 XX Review Writer | `llm_response` | review JSON |
| A23 | Text/Secret Input | value | 07 XX Review Writer | `mongo_uri` | 선택. writer override |
| A24 | Text Input | value | 07 XX Review Writer | `mongo_database` | 선택. writer override |
| A25 | Text Input | value | 07 XX Review Writer | `collection_name` | 선택. writer override도 full collection name으로 입력 |
| A27 | Text Input | value | 07 XX Review Writer | `duplicate_action` | 선택. writer override |
| A28 | 07 XX Review Writer | `payload_out` | 08 XX Authoring Response Builder | `payload` | 최종 응답 생성 |
| A29 | 08 XX Authoring Response Builder | `message` | Chat Output | `message` | 사용자 표시용 |
| A30 | 08 XX Authoring Response Builder | `api_response` | API/Debug output | data | 선택. 시스템 연동용 |

### 4.3 Authoring 운영 규칙

- LLM-2가 만든 metadata 후보를 바로 MongoDB에 쓰지 않는다.
- 반드시 04 normalizer, 05 similarity checker, 06 review prompt, LLM-3 review, 07 writer를 거친다.
- `review.ready_to_save=false`이면 07 writer는 저장하지 않아야 한다.
- 05가 duplicate decision을 요구하고 `duplicate_action=ask`이면 07 writer는 저장하지 않는다.
- collection 기본값:
  - domain: `agent_v2_domain_items`
  - table catalog: `agent_v2_table_catalog_items`
  - main flow filter: `agent_v2_main_flow_filters`
  - 다른 collection을 쓰는 경우 prefix가 아니라 full collection name을 그대로 입력한다.

## 5. 구현 후 확인 순서

v2 base에서 Langflow canvas를 만든 뒤 아래 순서로 확인한다.

1. `metadata_source=local`, dummy retrieval로 main flow smoke test
2. 16개 regression 질문 중 1~2개를 Playground에서 수동 실행
3. follow-up 질문에서 08 state가 다음 00 state로 들어가는지 확인
4. source_type별 retriever를 merger에 연결하고 `source_results` shape 확인
5. MongoDB metadata load를 `metadata_source=mongodb`로 전환
6. authoring flow는 먼저 `duplicate_action=ask`와 부족한 입력 케이스로 저장 차단을 확인
7. 운영 source credential을 붙인 뒤 live source smoke test

로컬 코드 검증 명령:

```powershell
cd C:\Users\qkekt\Desktop\metadata_driven_v2
python -m compileall -q reference_runtime langflow_components tools tests
python -m pytest tests -q
python tools\validate_regression.py
python tools\upload_json_to_mongodb.py --dry-run
python tools\validate_llm_in_loop.py --limit 1
```
