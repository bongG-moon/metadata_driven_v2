# Component LLM Validation Report

- Path: numbered Langflow components with Gemini intent/pandas nodes

## PASS da_wip_top_product

- PASS normalized_expected_intent_type
  - expected: `single_retrieval_analysis`
  - actual: `single_retrieval_analysis`
- PASS normalized_expected_analysis_kind
  - expected: `rank_top_n`
  - actual: `rank_top_n`
- PASS normalized_expected_datasets
  - expected: `['wip_today']`
  - actual: `['wip_today']`
- PASS expected_columns
  - expected: `['WIP']`
  - actual: `['TECH', 'DEN', 'MODE', 'PKG_TYPE1', 'PKG_TYPE2', 'LEAD', 'MCP_NO', 'WIP', 'OPER_NAME']`
- PASS non_empty_result
  - expected: `row_count > 0`
  - actual: `1`
- PASS expected_filter_fields
  - expected: `['OPER_NAME']`
  - actual: `['DATE', 'OPER_NAME']`
