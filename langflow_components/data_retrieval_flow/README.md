# Data Retrieval Flow Components

These standalone files mirror the existing four-source retrieval pattern:

- `02_oracle_query_retriever.py`: `source_type=oracle`
- `03_h_api_retriever.py`: `source_type=h_api`
- `04_datalake_retriever.py`: `source_type=datalake`
- `05_goodocs_retriever.py`: `source_type=goodocs`
- `01_dummy_data_retriever.py`: all-purpose local dummy source
- `06_source_retrieval_merger.py`: merges source-specific payloads

The current implementation returns deterministic dummy rows when live credentials are empty. When credentials are provided, the source retrievers execute the metadata-backed live branch:

- Oracle renders `source_config.query_template` with job `params` and executes it through `oracledb`.
- H-API sends `{"bindParams": [...]}` to `source_config.api_url` and extracts rows from `response_path` when configured.
- Datalake uses the LakeHouse runtime path: set `LAKEHOUSE_*` environment values, run `lakes.LakeHouse(...).ensure_running(...)`, execute SQL with `auto_run_sync_paragraph`, then read `get_rst()`.
- Goodocs loads the configured document through a `Goodocs` adapter/module and applies metadata filters such as `DATE`.

## How To Connect

### Dummy Only

Use only `01 Dummy Data Retriever`.

```text
04 Intent Plan Normalizer.payload_out -> 01 Dummy Data Retriever.payload
04 Intent Plan Normalizer.payload_out -> 05 Retrieval Payload Adapter.main_payload
01 Dummy Data Retriever.retrieval_payload -> 05 Retrieval Payload Adapter.retrieval_payload
05 Retrieval Payload Adapter.payload -> 06 Pandas Prompt Builder.payload
05 Retrieval Payload Adapter.payload -> 07 Pandas Code Executor.payload
```

Do not use `06 Source Retrieval Merger` in this dummy-only path.

### Four Source Split

Connect the same `04 Intent Plan Normalizer.payload_out` to all four source retrievers. Each retriever will only process jobs whose `source_type` matches its source.

```text
04 Intent Plan Normalizer.payload_out -> 02 Oracle Query Retriever.payload
04 Intent Plan Normalizer.payload_out -> 03 H-API Retriever.payload
04 Intent Plan Normalizer.payload_out -> 04 Datalake Retriever.payload
04 Intent Plan Normalizer.payload_out -> 05 Goodocs Retriever.payload
04 Intent Plan Normalizer.payload_out -> 05 Retrieval Payload Adapter.main_payload

02 Oracle Query Retriever.retrieval_payload -> 06 Source Retrieval Merger.oracle_retrieval
03 H-API Retriever.retrieval_payload -> 06 Source Retrieval Merger.h_api_retrieval
04 Datalake Retriever.retrieval_payload -> 06 Source Retrieval Merger.datalake_retrieval
05 Goodocs Retriever.retrieval_payload -> 06 Source Retrieval Merger.goodocs_retrieval

06 Source Retrieval Merger.retrieval_payload -> 05 Retrieval Payload Adapter.retrieval_payload
05 Retrieval Payload Adapter.payload -> 06 Pandas Prompt Builder.payload
05 Retrieval Payload Adapter.payload -> 07 Pandas Code Executor.payload
```

## Live Inputs

| Node | Inputs for live retrieval |
| --- | --- |
| `02 Oracle Query Retriever` | `oracle_config`, `fetch_limit` |
| `03 H-API Retriever` | `api_token`, `fetch_limit` |
| `04 Datalake Retriever` | `lakehouse_user_id`, `lakehouse_token`, `lakehouse_s3_access_key`, `lakehouse_s3_secret_key`, `fetch_limit` |
| `05 Goodocs Retriever` | `user_id`, `token_source`, `token_key`, optional `goodocs_module_name`, `fetch_limit` |

`source_config` comes from table catalog metadata and is attached to each `retrieval_jobs[]` item by the main flow normalizer. Credentials stay in Langflow node inputs or environment variables, not in metadata.
