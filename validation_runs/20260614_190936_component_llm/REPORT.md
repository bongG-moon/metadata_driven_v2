# Component LLM Validation Report

- Path: numbered Langflow components with Gemini intent/pandas nodes

## PASS today_da_wip_production_target_rate

- PASS normalized_expected_intent_type
  - expected: `multi_source_analysis`
  - actual: `multi_source_analysis`
- PASS normalized_expected_analysis_kind
  - expected: `production_wip_target_rate`
  - actual: `production_wip_target_rate`
- PASS normalized_expected_datasets
  - expected: `['production_today', 'target', 'wip_today']`
  - actual: `['production_today', 'target', 'wip_today']`
- PASS expected_columns
  - expected: `['ACHIEVEMENT_RATE', 'OUT_PLAN', 'PRODUCTION', 'WIP']`
  - actual: `['TECH', 'DEN', 'MODE', 'PKG_TYPE1', 'PKG_TYPE2', 'LEAD', 'MCP_NO', 'WIP', 'PRODUCTION', 'OUT_PLAN', 'ACHIEVEMENT_RATE']`
- PASS non_empty_result
  - expected: `row_count > 0`
  - actual: `8`
- PASS expected_filter_fields
  - expected: `['OPER_NAME', 'DATE']`
  - actual: `['DATE', 'OPER_NAME']`
