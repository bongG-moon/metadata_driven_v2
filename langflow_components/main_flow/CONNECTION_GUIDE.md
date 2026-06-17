# Main Flow Connection Guide

This guide is based on the files in `langflow_components/main_flow`.

> Compatibility note: `main_flow` is the combined single-canvas flow kept for existing deployments. New runtime wiring should prefer `router_flow -> metadata_qa_flow | data_analysis_flow | report_generation_flow | operations_diagnosis_flow`.

## Design Decisions

- Metadata/help/catalog questions are handled inside `main_flow` by `03 Route Candidate Builder`, `04` route prompt + route LLM, `05 Route Classifier Normalizer`, and `06 Metadata QA Response Builder`.
- The metadata QA branch still runs before the intent LLM. This is intentional: metadata questions do not need data retrieval, pandas execution, or result storage, and routing them before the heavy analysis path prevents catalog/help questions from drifting into normal data analysis.
- `03` does not classify metadata question types by keyword. It builds metadata-backed candidates such as candidate dataset/family/quantity term, then the small route LLM classifies the question type.
- `03` can resolve natural business terms through `domain_items.quantity_terms` as candidate context. For example, "생산량 데이터를 조회하는 쿼리" can provide `production_today` as a candidate without the user saying `production_today`.
- If a static Langflow canvas cannot conditionally skip LLM-R, it is safe to keep LLM-R wired for every turn because `05` ignores `llm_response` whenever `route_llm_required=false`. A web/API orchestrator can skip the LLM-R call only for those direct cases, such as a short greeting.
- `target_dataset` in `metadata_route` is only a metadata-QA target pointer for dataset detail/query/example answers. It is not the analysis dataset list; normal analysis datasets are still chosen later by `07`/`08`.
- `07 Intent Prompt Builder` still supports `direct_response_ready=true`. When metadata QA has already prepared a direct answer, node `07` emits a small skip prompt and downstream nodes pass the payload through.
- The first `01 MongoDB Data Loader` is optional. If the caller passes compact previous `state.current_data` with `data_ref`, `row_count`, `columns`, preview `rows`, and product key summary, `00 Request State Loader` is enough.
- Keep the second `01 MongoDB Data Loader` after `08 Intent Plan Normalizer` with `restore_mode=auto`. It loads full previous rows only when the normalized intent sets `requires_full_previous_result_restore=true` or `previous_result_restore_mode=full`.
- `18 MongoDB Data Store` belongs immediately after `17 Pandas Code Executor`. It stores both original retrieval rows and pandas result rows, then leaves compact previews and `data_ref` pointers in the payload.

## Node Inventory

| # | Node | Component file | Required inputs | Outputs |
| --- | --- | --- | --- | --- |
| 00 | `00 Request State Loader` | `00_request_state_loader.py` | `question`, `session_id`, optional `state` | `payload` |
| 01 | `01 MongoDB Data Loader` | `01_mongodb_data_loader.py` | `payload` | `payload_out` |
| 02 | `02 Metadata Context Loader` | `02_metadata_context_loader.py` | `payload` | `payload_out` |
| 03 | `03 Route Candidate Builder` | `03_route_candidate_builder.py` | `payload` | `payload_out` |
| 04 | `04 Route Classifier Prompt Builder` | `04_route_classifier_prompt_builder.py` | `payload` | `route_prompt`, `prompt_payload` |
| LLM-R | Route Classifier LLM | Langflow LLM node | prompt/message | text/message |
| 05 | `05 Route Classifier Normalizer` | `05_route_classifier_normalizer.py` | `payload`, optional `llm_response` | `payload_out` |
| 06 | `06 Metadata QA Response Builder` | `06_metadata_qa_response_builder.py` | `payload` | `payload_out`, `message` |
| 07 | `07 Intent Prompt Builder` | `07_intent_prompt_builder.py` | `payload` | `intent_prompt`, `prompt_payload` |
| LLM-A | Intent LLM | Langflow LLM node | prompt/message | text/message |
| 08 | `08 Intent Plan Normalizer` | `08_intent_plan_normalizer.py` | `payload`, `llm_response` | `payload_out` |
| 09 | `09 Dummy Data Retriever` | `09_dummy_data_retriever.py` | `payload` | `retrieval_payload` |
| 10 | `10 Oracle Query Retriever` | `10_oracle_query_retriever.py` | `payload`, optional Oracle config | `retrieval_payload` |
| 11 | `11 H-API Retriever` | `11_h_api_retriever.py` | `payload`, optional token | `retrieval_payload` |
| 12 | `12 Datalake Retriever` | `12_datalake_retriever.py` | `payload`, optional lakehouse credentials | `retrieval_payload` |
| 13 | `13 Goodocs Retriever` | `13_goodocs_retriever.py` | `payload`, optional Goodocs credentials | `retrieval_payload` |
| 14 | `14 Source Retrieval Merger` | `14_source_retrieval_merger.py` | source retrieval payloads | `retrieval_payload` |
| 15 | `15 Retrieval Payload Adapter` | `15_retrieval_payload_adapter.py` | `main_payload`, `retrieval_payload` | `payload` |
| 16 | `16 Pandas Prompt Builder` | `16_pandas_prompt_builder.py` | `payload` | `pandas_prompt`, `prompt_payload` |
| LLM-B | Pandas Code LLM | Langflow LLM node | prompt/message | text/message |
| 17 | `17 Pandas Code Executor` | `17_pandas_code_executor.py` | `payload`, `llm_response` | `payload_out` |
| 18 | `18 MongoDB Data Store` | `18_mongodb_data_store.py` | `payload` | `payload_out` |
| 19 | `19 Answer Prompt Builder` | `19_answer_prompt_builder.py` | `payload` | `answer_prompt`, `prompt_payload` |
| LLM-C | Answer LLM | Langflow LLM node | prompt/message | text/message |
| 20 | `20 Answer Response Builder` | `20_answer_response_builder.py` | `payload`, `llm_response` | `payload_out` |
| 21 | `21 Answer Message Adapter` | `21_answer_message_adapter.py` | `payload` | `message` |
| 22 | `22 Main Flow API Response Builder` | `22_api_response_builder.py` | `payload` | `api_response`, `api_message` |

## Recommended Canvas Sequence

```text
Chat Input
-> 00 Request State Loader
-> 02 Metadata Context Loader
-> 03 Route Candidate Builder
-> 04 Route Classifier Prompt Builder
-> Route Classifier LLM (only when `route_llm_required=true`)
-> 05 Route Classifier Normalizer
-> 06 Metadata QA Response Builder
-> 07 Intent Prompt Builder
-> Intent LLM
-> 08 Intent Plan Normalizer
-> 01 MongoDB Data Loader (second instance, restore_mode=auto)
-> 09/10/11/12/13 source retriever nodes
-> 14 Source Retrieval Merger
-> 15 Retrieval Payload Adapter
-> 16 Pandas Prompt Builder
-> Pandas Code LLM
-> 17 Pandas Code Executor
-> 18 MongoDB Data Store
-> 19 Answer Prompt Builder
-> Answer LLM
-> 20 Answer Response Builder
-> 21 Answer Message Adapter
-> Chat Output

parallel:
20 Answer Response Builder -> 22 Main Flow API Response Builder -> API/Data Output
```

If the client cannot pass compact previous state and only has a MongoDB `data_ref`, insert an optional first loader:

```text
00 Request State Loader
-> 01 MongoDB Data Loader (optional first instance, restore_mode=preview)
-> 02 Metadata Context Loader
```

## Required Branch Connections

| # | From node | From output | To node | To input | Note |
| --- | --- | --- | --- | --- | --- |
| 1 | `Chat Input` | message/text | `00 Request State Loader` | `question` | User question |
| 2 | State store/web backend | Data | `00 Request State Loader` | `state` | Compact previous state |
| 3 | `00 Request State Loader` | `payload` | `02 Metadata Context Loader` | `payload` | Preferred path when state already has preview/summary |
| 3B | `00 Request State Loader` | `payload` | optional first `01 MongoDB Data Loader` | `payload` | Only when previous state needs preview hydration from MongoDB |
| 3C | optional first `01 MongoDB Data Loader` | `payload_out` | `02 Metadata Context Loader` | `payload` | Optional preview-restored state |
| 4 | `02 Metadata Context Loader` | `payload_out` | `03 Route Candidate Builder` | `payload` | Metadata-backed route candidates |
| 5 | `03 Route Candidate Builder` | `payload_out` | `04 Route Classifier Prompt Builder` | `payload` | Build question-type route prompt |
| 6 | `04 Route Classifier Prompt Builder` | `route_prompt` | Route Classifier LLM | prompt/message | Small JSON route decision; can be skipped only when `route_llm_required=false` |
| 7 | `03 Route Candidate Builder` | `payload_out` | `05 Route Classifier Normalizer` | `payload` | Main route payload branch |
| 8 | Route Classifier LLM | text/message | `05 Route Classifier Normalizer` | `llm_response` | Route JSON; blank is ok only when `route_llm_required=false` |
| 9 | `05 Route Classifier Normalizer` | `payload_out` | `06 Metadata QA Response Builder` | `payload` | Direct answer or pass-through |
| 10 | `06 Metadata QA Response Builder` | `payload_out` | `07 Intent Prompt Builder` | `payload` | Direct answers produce skip prompt |
| 11 | `07 Intent Prompt Builder` | `intent_prompt` | Intent LLM | prompt/message | JSON intent |
| 12 | `06 Metadata QA Response Builder` | `payload_out` | `08 Intent Plan Normalizer` | `payload` | Main payload branch |
| 13 | Intent LLM | text/message | `08 Intent Plan Normalizer` | `llm_response` | Intent JSON response |
| 14 | `08 Intent Plan Normalizer` | `payload_out` | second `01 MongoDB Data Loader` | `payload` | Set this loader to `restore_mode=auto` |
| 15 | second `01 MongoDB Data Loader` | `payload_out` | source retriever nodes `09`~`13` | `payload` | Source-specific retrieval |
| 16 | `10/11/12/13` | `retrieval_payload` | `14 Source Retrieval Merger` | matching source input | Merge real source payloads |
| 17 | `14 Source Retrieval Merger` | `retrieval_payload` | `15 Retrieval Payload Adapter` | `retrieval_payload` | Unified source rows |
| 18 | second `01 MongoDB Data Loader` | `payload_out` | `15 Retrieval Payload Adapter` | `main_payload` | Main payload branch |
| 19 | `15 Retrieval Payload Adapter` | `payload` | `16 Pandas Prompt Builder` | `payload` | Build pandas prompt |
| 20 | `15 Retrieval Payload Adapter` | `payload` | `17 Pandas Code Executor` | `payload` | Payload branch for executor |
| 21 | Pandas Code LLM | text/message | `17 Pandas Code Executor` | `llm_response` | JSON pandas code |
| 22 | `17 Pandas Code Executor` | `payload_out` | `18 MongoDB Data Store` | `payload` | Store source/result rows |
| 23 | `18 MongoDB Data Store` | `payload_out` | `19 Answer Prompt Builder` | `payload` | Build final answer prompt |
| 24 | `18 MongoDB Data Store` | `payload_out` | `20 Answer Response Builder` | `payload` | Carry compact `data_ref` |
| 25 | Answer LLM | text/message | `20 Answer Response Builder` | `llm_response` | Final answer |
| 26 | `20 Answer Response Builder` | `payload_out` | `21 Answer Message Adapter` | `payload` | Playground markdown |
| 27 | `20 Answer Response Builder` | `payload_out` | `22 Main Flow API Response Builder` | `payload` | Web/API JSON |
| 28 | `20 Answer Response Builder` | `payload_out.state` | State store/web backend | stored state | Use as next turn `00.state` |

## Previous State Contract

`00 Request State Loader` is enough when the caller passes this compact state:

```json
{
  "chat_history": [],
  "context": {},
  "current_data": {
    "columns": ["MODE", "WIP"],
    "rows": [{"MODE": "LPDDR5", "WIP": 10}],
    "row_count": 100,
    "data_ref": {"store": "mongodb", "ref_id": "..."},
    "source_dataset_keys": ["wip_today"],
    "source_aliases": ["wip_data"],
    "product_key_columns": ["MODE"],
    "product_key_values": [{"MODE": "LPDDR5"}],
    "product_key_count": 1
  },
  "followup_source_results": []
}
```

The optional first `01 MongoDB Data Loader` exists for compatibility with states that have only `data_ref` and no preview rows/summary. It should use `restore_mode=preview`.

## Metadata QA Policy

Metadata QA answers are metadata-backed after question-type routing:

- Greeting/help questions return a direct guide and a few example questions.
- Data list questions return dataset keys, display names, source types, families, required params, and quantity columns.
- Dataset example questions return examples only for the requested dataset.
- Dataset query questions return registered `source_config.query_template`.
- Domain questions search registered domain metadata.

When `direct_response_ready=true`, downstream analysis and answer nodes pass through the payload. `18 MongoDB Data Store` does not store metadata QA rows in the result collection.

## Full Restore Policy

Default follow-up planning uses only compact state: `data_ref`, `row_count`, `columns`, preview rows, and product key summary.

Full restore is requested only after intent normalization when the question needs the previous result rows themselves, for example:

- Re-show all/detail/original rows from the previous result.
- Re-sort, filter, rank, regroup, or aggregate the previous result.
- LLM intent explicitly sets `requires_full_previous_result_restore=true` or `previous_result_restore_mode=full`.

Questions such as "이 제품의 할당 장비 대수 알려줘" usually need only previous product keys plus a new `equipment_status` retrieval, so summary state is enough.

## MongoDB Config Inputs

| Target node | Input | Recommended value |
| --- | --- | --- |
| optional first `01 MongoDB Data Loader` | `restore_mode` | `preview` |
| optional first `01 MongoDB Data Loader` | `preview_row_limit` | `5` |
| second `01 MongoDB Data Loader` | `restore_mode` | `auto` |
| second `01 MongoDB Data Loader` | `preview_row_limit` | `5` |
| `02 Metadata Context Loader` | `domain_collection_name` | `agent_v2_domain_items` |
| `02 Metadata Context Loader` | `table_catalog_collection_name` | `agent_v2_table_catalog_items` |
| `02 Metadata Context Loader` | `main_flow_filter_collection_name` | `agent_v2_main_flow_filters` |
| `18 MongoDB Data Store` | `result_collection_name` | `agent_v2_result_store` or `MONGODB_RESULT_COLLECTION` |
| `18 MongoDB Data Store` | `preview_row_limit` | `5` |
| `18 MongoDB Data Store` | `min_rows` | `1` |

Metadata collections and result-store collections are full collection names, not prefix combinations.


