# Data Retrieval Flow Connection Guide

이 flow는 main flow의 `04 Intent Plan Normalizer.payload_out`을 받아 dataset별 retrieval 결과를 `retrieval_payload`로 반환합니다. 실제 운영에서는 source별 component 내부의 dummy fallback 부분을 실제 Oracle/H-API/Datalake/Goodocs 호출로 교체합니다.

## Option A. Dummy Retrieval

검증이나 Langflow wiring 확인용입니다. `01 Dummy Data Retriever`가 모든 retrieval job을 처리합니다.

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| 1 | Main `04 Intent Plan Normalizer` | `payload_out` | `01 Dummy Data Retriever` | `payload` |
| 2 | `01 Dummy Data Retriever` | `retrieval_payload` | Main `05 Retrieval Payload Adapter` | `retrieval_payload` |
| 3 | Main `04 Intent Plan Normalizer` | `payload_out` | Main `05 Retrieval Payload Adapter` | `main_payload` |

## Option B. Four Source Retrieval

운영에 가까운 구조입니다. 모든 source retriever가 같은 payload를 받지만, 각 component는 자기 source_type에 해당하는 job만 처리합니다.

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| 1 | Main `04 Intent Plan Normalizer` | `payload_out` | `02 Oracle Query Retriever` | `payload` |
| 2 | Main `04 Intent Plan Normalizer` | `payload_out` | `03 H-API Retriever` | `payload` |
| 3 | Main `04 Intent Plan Normalizer` | `payload_out` | `04 Datalake Retriever` | `payload` |
| 4 | Main `04 Intent Plan Normalizer` | `payload_out` | `05 Goodocs Retriever` | `payload` |
| 5 | `02 Oracle Query Retriever` | `retrieval_payload` | `06 Source Retrieval Merger` | `oracle_retrieval` |
| 6 | `03 H-API Retriever` | `retrieval_payload` | `06 Source Retrieval Merger` | `h_api_retrieval` |
| 7 | `04 Datalake Retriever` | `retrieval_payload` | `06 Source Retrieval Merger` | `datalake_retrieval` |
| 8 | `05 Goodocs Retriever` | `retrieval_payload` | `06 Source Retrieval Merger` | `goodocs_retrieval` |
| 9 | `06 Source Retrieval Merger` | `retrieval_payload` | Main `05 Retrieval Payload Adapter` | `retrieval_payload` |
| 10 | Main `04 Intent Plan Normalizer` | `payload_out` | Main `05 Retrieval Payload Adapter` | `main_payload` |

## Source Inputs

| Node | Data input | Config inputs |
| --- | --- | --- |
| `02 Oracle Query Retriever` | `payload` | `oracle_config`, `fetch_limit` |
| `03 H-API Retriever` | `payload` | `api_token`, `fetch_limit` |
| `04 Datalake Retriever` | `payload` | `lake_user_id`, `lake_jwt_token`, `fetch_limit` |
| `05 Goodocs Retriever` | `payload` | `goodocs_user_id`, `goodocs_token`, `fetch_limit` |

## Output Contract

`retrieval_payload`에는 다음 정도만 유지합니다.

- `source_results[].dataset_key`
- `source_results[].source_alias`
- `source_results[].rows`
- `source_results[].columns`
- `source_results[].row_count`
- `source_results[].applied_params`
- `source_results[].applied_filters`
- `source_results[].data_ref`
