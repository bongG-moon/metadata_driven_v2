# Data Retrieval Flow Components

These standalone files mirror the existing four-source retrieval pattern:

- `02_oracle_query_retriever.py`: `source_type=oracle`
- `03_h_api_retriever.py`: `source_type=h_api`
- `04_datalake_retriever.py`: `source_type=datalake`
- `05_goodocs_retriever.py`: `source_type=goodocs`
- `01_dummy_data_retriever.py`: all-purpose local dummy source
- `06_source_retrieval_merger.py`: merges source-specific payloads

The current implementation returns deterministic dummy rows when live credentials are empty. This keeps Langflow wiring and pandas validation close to the real source split without requiring Oracle, H-API, Datalake, or Goodocs access on a developer machine.

## How To Connect

### Dummy Only

Use only `01 Dummy Data Retriever`.

```text
03 Intent Plan Normalizer.payload_out -> 01 Dummy Data Retriever.payload
03 Intent Plan Normalizer.payload_out -> 04 Retrieval Payload Adapter.main_payload
01 Dummy Data Retriever.retrieval_payload -> 04 Retrieval Payload Adapter.retrieval_payload
04 Retrieval Payload Adapter.payload -> 05 Pandas Prompt Builder.payload
04 Retrieval Payload Adapter.payload -> 06 Pandas Code Executor.payload
```

Do not use `06 Source Retrieval Merger` in this dummy-only path.

### Four Source Split

Connect the same `03 Intent Plan Normalizer.payload_out` to all four source retrievers. Each retriever will only process jobs whose `source_type` matches its source.

```text
03 Intent Plan Normalizer.payload_out -> 02 Oracle Query Retriever.payload
03 Intent Plan Normalizer.payload_out -> 03 H-API Retriever.payload
03 Intent Plan Normalizer.payload_out -> 04 Datalake Retriever.payload
03 Intent Plan Normalizer.payload_out -> 05 Goodocs Retriever.payload
03 Intent Plan Normalizer.payload_out -> 04 Retrieval Payload Adapter.main_payload

02 Oracle Query Retriever.retrieval_payload -> 06 Source Retrieval Merger.oracle_retrieval
03 H-API Retriever.retrieval_payload -> 06 Source Retrieval Merger.h_api_retrieval
04 Datalake Retriever.retrieval_payload -> 06 Source Retrieval Merger.datalake_retrieval
05 Goodocs Retriever.retrieval_payload -> 06 Source Retrieval Merger.goodocs_retrieval

06 Source Retrieval Merger.retrieval_payload -> 04 Retrieval Payload Adapter.retrieval_payload
04 Retrieval Payload Adapter.payload -> 05 Pandas Prompt Builder.payload
04 Retrieval Payload Adapter.payload -> 06 Pandas Code Executor.payload
```
