# Data Retrieval Flow Connection Guide

이 flow는 main flow의 `04 Intent Plan Normalizer.payload_out`을 받아 dataset별 retrieval 결과를 `retrieval_payload`로 반환합니다. `04 Intent Plan Normalizer`가 metadata의 `source_type`과 `source_config`를 `retrieval_jobs[]`에 붙이고, source별 component는 자기 `source_type` job만 처리합니다.

credential/config 입력이 비어 있으면 deterministic dummy fallback을 반환합니다. 운영 credential을 넣으면 각 component가 실제 Oracle/H-API/Datalake/Goodocs 조회 branch를 실행합니다.

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
| `04 Datalake Retriever` | `payload` | `lakehouse_user_id`, `lakehouse_token`, `lakehouse_s3_access_key`, `lakehouse_s3_secret_key`, `fetch_limit` |
| `05 Goodocs Retriever` | `payload` | `user_id`, `token_source`, `token_key`, `goodocs_module_name`, `fetch_limit` |

## Source Config Contract

metadata table catalog의 `source_config`는 credential을 담지 않고 실행 대상 정보만 담습니다.

| source_type | Required `source_config` |
| --- | --- |
| `oracle` | `db_key`, `query_template` |
| `h_api` | `api_url`, optional `response_path` |
| `datalake` | `query_template`, optional `cluster_type` |
| `goodocs` | `doc_id`, optional `sheet_name` |

Oracle의 `oracle_config`는 JSON 또는 TNS block을 받을 수 있습니다. 예:

```json
{
  "PNT_RPT": {
    "user": "USER_ID",
    "password": "PASSWORD",
    "dsn": "(DESCRIPTION=...)"
  }
}
```

Datalake는 `lakes.LakeHouse` 방식으로 실행합니다. component가 `LAKEHOUSE_USER_ID`, `LAKEHOUSE_TOKEN`, `LAKEHOUSE_S3_ACCESS_KEY`, `LAKEHOUSE_S3_SECRET_KEY` 환경값을 입력값으로 세팅한 뒤 `ensure_running(cluster_type="starrocks")`, `auto_run_sync_paragraph(code=sql)`, `get_rst()` 순서로 rows를 가져옵니다.

## Output Contract

`retrieval_payload`에는 다음 정도만 유지합니다.

- `source_results[].dataset_key`
- `source_results[].source_alias`
- `source_results[].rows`
- `source_results[].columns`
- `source_results[].row_count`
- `source_results[].applied_params`
- `source_results[].applied_filters`
- `source_results[].data`
- `source_results[].data_ref`는 main flow `05 Retrieval Payload Adapter`가 compact result로 바꿀 때 생성합니다.
