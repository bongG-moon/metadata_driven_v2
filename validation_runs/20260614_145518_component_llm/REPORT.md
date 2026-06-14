# Component LLM Validation Report

- Path: numbered Langflow components with Gemini intent/pandas nodes

## PASS multi_step_rank_wip_with_production

- PASS normalized_expected_intent_type
  - expected: `multi_step_analysis`
  - actual: `multi_step_analysis`
- PASS normalized_expected_analysis_kind
  - expected: `rank_wip_then_join_production`
  - actual: `rank_wip_then_join_production`
- PASS normalized_expected_datasets
  - expected: `['production_today', 'wip_today']`
  - actual: `['production_today', 'wip_today']`
- PASS expected_columns
  - expected: `['PRODUCTION', 'RANK_GROUP', 'WIP']`
  - actual: `['RANK_GROUP', 'WIP_RANK', 'TECH', 'DEN', 'MODE', 'PKG_TYPE1', 'PKG_TYPE2', 'LEAD', 'MCP_NO', 'WIP', 'PRODUCTION']`
- PASS non_empty_result
  - expected: `row_count > 0`
  - actual: `36`
- PASS expected_filter_fields
  - expected: `['OPER_NAME']`
  - actual: `['DATE', 'OPER_NAME']`
- PASS expected_params_by_dataset
  - expected: `{'wip_today': {'DATE': '20260612'}, 'production_today': {'DATE': '20260612'}}`
  - actual: `{'wip_today': [{'DATE': '20260612'}], 'production_today': [{'DATE': '20260612'}]}`

## PASS hold_history_detail

- PASS normalized_expected_intent_type
  - expected: `detail_lookup`
  - actual: `detail_lookup`
- PASS normalized_expected_analysis_kind
  - expected: `detail_rows`
  - actual: `detail_rows`
- PASS normalized_expected_datasets
  - expected: `['hold_history']`
  - actual: `['hold_history']`
- PASS expected_columns
  - expected: `['HOLD_CD', 'HOLD_DESC', 'HOLD_TM', 'LOT_ID']`
  - actual: `['LOT_ID', 'HOLD_TM', 'HOLD_CD', 'HOLD_DESC', 'HOLD_USER_ID', 'EVENT_CD']`
- PASS non_empty_result
  - expected: `row_count > 0`
  - actual: `2`
- PASS expected_filter_fields
  - expected: `['LOT_ID']`
  - actual: `['LOT_ID']`
- PASS expected_params_by_dataset
  - expected: `{'hold_history': {'LOT_ID': 'T1234567GEN1'}}`
  - actual: `{'hold_history': [{'LOT_ID': 'T1234567GEN1'}]}`

## PASS hold_lot_list

- PASS normalized_expected_intent_type
  - expected: `detail_lookup`
  - actual: `detail_lookup`
- PASS normalized_expected_analysis_kind
  - expected: `detail_rows`
  - actual: `detail_rows`
- PASS normalized_expected_datasets
  - expected: `['lot_status']`
  - actual: `['lot_status']`
- PASS expected_columns
  - expected: `['LOT_HOLD_STAT_CD', 'LOT_ID']`
  - actual: `['LOT_ID', 'OPER_SHORT_DESC', 'LOT_STAT_CD', 'LOT_HOLD_STAT_CD', 'TECH', 'DEN', 'MODE', 'PKG_TYPE1', 'PKG_TYPE2', 'LEAD', 'MCP_NO', 'SUB_PROD_QTY', 'WF_QTY', 'IN_TAT', 'CUM_TAT']`
- PASS non_empty_result
  - expected: `row_count > 0`
  - actual: `161`
- PASS expected_filter_fields
  - expected: `['LOT_HOLD_STAT_CD']`
  - actual: `['LOT_HOLD_STAT_CD']`

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
  - actual: `['TECH', 'DEN', 'MODE', 'PKG_TYPE1', 'PKG_TYPE2', 'LEAD', 'MCP_NO', 'WIP']`
- PASS non_empty_result
  - expected: `row_count > 0`
  - actual: `1`
- PASS expected_filter_fields
  - expected: `['OPER_NAME']`
  - actual: `['DATE', 'OPER_NAME']`

## PASS followup_equipment_for_product

- PASS normalized_expected_intent_type
  - expected: `followup_transform`
  - actual: `followup_transform`
- PASS normalized_expected_analysis_kind
  - expected: `equipment_for_previous_products`
  - actual: `equipment_for_previous_products`
- PASS normalized_expected_datasets
  - expected: `['equipment_status']`
  - actual: `['equipment_status']`
- PASS expected_columns
  - expected: `['EQPID', 'EQP_MODEL']`
  - actual: `['EQPID', 'EQP_MODEL', 'PRESS_CNT', 'MODE', 'TECH', 'DEN', 'PKG_TYPE1', 'PKG_TYPE2', 'LEAD', 'MCP_NO', 'LOT_ID', 'RECIPE_ID']`
- PASS non_empty_result
  - expected: `row_count > 0`
  - actual: `3`
- PASS expected_filter_fields
  - expected: `['PRODUCT_GRAIN']`
  - actual: `['DEN', 'LEAD', 'MCP_NO', 'MODE', 'PKG_TYPE1', 'PKG_TYPE2', 'PRODUCT_GRAIN', 'TECH']`
- PASS followup_uses_state
  - expected: `state_product_keys not empty`
  - actual: `[{'TECH': 'POP', 'DEN': '128G', 'MODE': 'MCP', 'PKG_TYPE1': 'LFBGA', 'PKG_TYPE2': 'MCP', 'LEAD': 'LF', 'MCP_NO': 'L-269M2B'}]`

## PASS lpddr5_wb_production_and_wip

- PASS normalized_expected_intent_type
  - expected: `multi_source_analysis`
  - actual: `multi_source_analysis`
- PASS normalized_expected_analysis_kind
  - expected: `aggregate_join`
  - actual: `aggregate_join`
- PASS normalized_expected_datasets
  - expected: `['production_today', 'wip_today']`
  - actual: `['production_today', 'wip_today']`
- PASS expected_columns
  - expected: `['PRODUCTION', 'WIP']`
  - actual: `['TECH', 'DEN', 'MODE', 'PKG_TYPE1', 'PKG_TYPE2', 'LEAD', 'MCP_NO', 'PRODUCTION', 'WIP']`
- PASS non_empty_result
  - expected: `row_count > 0`
  - actual: `2`
- PASS expected_filter_fields
  - expected: `['MODE', 'OPER_NAME']`
  - actual: `['DATE', 'MODE', 'OPER_NAME']`

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

## PASS da1_low_output_vs_target

- PASS normalized_expected_intent_type
  - expected: `multi_source_analysis`
  - actual: `multi_source_analysis`
- PASS normalized_expected_analysis_kind
  - expected: `low_output_vs_target`
  - actual: `low_output_vs_target`
- PASS normalized_expected_datasets
  - expected: `['production_today', 'target']`
  - actual: `['production_today', 'target']`
- PASS expected_columns
  - expected: `['ACHIEVEMENT_RATE', 'BALANCE', 'LOW_OUTPUT_FLAG', 'PRODUCTION', 'TARGET_QTY']`
  - actual: `['TECH', 'DEN', 'MODE', 'PKG_TYPE1', 'PKG_TYPE2', 'LEAD', 'MCP_NO', 'PRODUCTION', 'TARGET_QTY', 'ACHIEVEMENT_RATE', 'BALANCE', 'LOW_OUTPUT_FLAG']`
- PASS non_empty_result
  - expected: `row_count > 0`
  - actual: `8`
- PASS expected_filter_fields
  - expected: `['OPER_NAME', 'DATE']`
  - actual: `['DATE', 'OPER_NAME']`

## PASS input_plan_vs_da_low_output

- PASS normalized_expected_intent_type
  - expected: `multi_source_analysis`
  - actual: `multi_source_analysis`
- PASS normalized_expected_analysis_kind
  - expected: `low_output_vs_target`
  - actual: `low_output_vs_target`
- PASS normalized_expected_datasets
  - expected: `['production_today', 'target']`
  - actual: `['production_today', 'target']`
- PASS expected_columns
  - expected: `['ACHIEVEMENT_RATE', 'BALANCE', 'LOW_OUTPUT_FLAG', 'PRODUCTION', 'TARGET_QTY']`
  - actual: `['TECH', 'DEN', 'MODE', 'PKG_TYPE1', 'PKG_TYPE2', 'LEAD', 'MCP_NO', 'PRODUCTION', 'TARGET_QTY', 'ACHIEVEMENT_RATE', 'BALANCE', 'LOW_OUTPUT_FLAG']`
- PASS non_empty_result
  - expected: `row_count > 0`
  - actual: `8`
- PASS expected_filter_fields
  - expected: `['OPER_NAME', 'DATE']`
  - actual: `['DATE', 'OPER_NAME']`

## PASS waiting_lot_count_by_process

- PASS normalized_expected_intent_type
  - expected: `single_retrieval_analysis`
  - actual: `single_retrieval_analysis`
- PASS normalized_expected_analysis_kind
  - expected: `lot_count_by_process`
  - actual: `lot_count_by_process`
- PASS normalized_expected_datasets
  - expected: `['lot_status']`
  - actual: `['lot_status']`
- PASS expected_columns
  - expected: `['LOT_COUNT', 'OPER_SHORT_DESC']`
  - actual: `['OPER_SHORT_DESC', 'LOT_COUNT']`
- PASS non_empty_result
  - expected: `row_count > 0`
  - actual: `10`
- PASS expected_filter_fields
  - expected: `['LOT_STAT_CD']`
  - actual: `['LOT_STAT_CD']`

## PASS da_lot_wafer_die_summary

- PASS normalized_expected_intent_type
  - expected: `single_retrieval_analysis`
  - actual: `single_retrieval_analysis`
- PASS normalized_expected_analysis_kind
  - expected: `lot_quantity_summary`
  - actual: `lot_quantity_summary`
- PASS normalized_expected_datasets
  - expected: `['lot_status']`
  - actual: `['lot_status']`
- PASS expected_columns
  - expected: `['DIE_QTY', 'LOT_COUNT', 'WF_QTY']`
  - actual: `['LOT_COUNT', 'WF_QTY', 'DIE_QTY']`
- PASS non_empty_result
  - expected: `row_count > 0`
  - actual: `1`
- PASS expected_filter_fields
  - expected: `['OPER_NAME']`
  - actual: `['OPER_NAME']`

## PASS da_wip_quantity_uses_wip_dataset

- PASS normalized_expected_intent_type
  - expected: `single_retrieval_analysis`
  - actual: `single_retrieval_analysis`
- PASS normalized_expected_analysis_kind
  - expected: `aggregate_wip_total`
  - actual: `aggregate_wip_total`
- PASS normalized_expected_datasets
  - expected: `['wip_today']`
  - actual: `['wip_today']`
- PASS expected_columns
  - expected: `['SCOPE', 'WIP']`
  - actual: `['SCOPE', 'WIP']`
- PASS non_empty_result
  - expected: `row_count > 0`
  - actual: `1`
- PASS expected_filter_fields
  - expected: `['OPER_NAME']`
  - actual: `['DATE', 'OPER_NAME']`
- PASS forbidden_filter_fields
  - expected: `not present: ['LOT_STAT_CD', 'LOT_HOLD_STAT_CD']`
  - actual: `[]`

## PASS overall_wip_scope_reset_after_da

- PASS normalized_expected_intent_type
  - expected: `single_retrieval_analysis`
  - actual: `single_retrieval_analysis`
- PASS normalized_expected_analysis_kind
  - expected: `aggregate_wip_total`
  - actual: `aggregate_wip_total`
- PASS normalized_expected_datasets
  - expected: `['wip_today']`
  - actual: `['wip_today']`
- PASS expected_columns
  - expected: `['SCOPE', 'WIP']`
  - actual: `['SCOPE', 'WIP']`
- PASS non_empty_result
  - expected: `row_count > 0`
  - actual: `1`
- PASS forbidden_filter_fields
  - expected: `not present: ['OPER_NAME', 'LOT_STAT_CD', 'LOT_HOLD_STAT_CD']`
  - actual: `[]`

## PASS today_total_production_wip_target

- PASS normalized_expected_intent_type
  - expected: `multi_source_analysis`
  - actual: `multi_source_analysis`
- PASS normalized_expected_analysis_kind
  - expected: `overall_production_wip_target`
  - actual: `overall_production_wip_target`
- PASS normalized_expected_datasets
  - expected: `['production_today', 'target', 'wip_today']`
  - actual: `['production_today', 'target', 'wip_today']`
- PASS expected_columns
  - expected: `['OUT_PLAN', 'PRODUCTION', 'WIP']`
  - actual: `['PRODUCTION', 'WIP', 'OUT_PLAN']`
- PASS non_empty_result
  - expected: `row_count > 0`
  - actual: `1`

## PASS yesterday_production_today_plan_gap

- PASS normalized_expected_intent_type
  - expected: `multi_source_analysis`
  - actual: `multi_source_analysis`
- PASS normalized_expected_analysis_kind
  - expected: `date_split_production_plan_gap`
  - actual: `date_split_production_plan_gap`
- PASS normalized_expected_datasets
  - expected: `['production', 'target']`
  - actual: `['production', 'target']`
- PASS expected_columns
  - expected: `['BALANCE', 'OUT_PLAN', 'PRODUCTION']`
  - actual: `['TECH', 'DEN', 'MODE', 'PKG_TYPE1', 'PKG_TYPE2', 'LEAD', 'MCP_NO', 'PRODUCTION', 'OUT_PLAN', 'BALANCE']`
- PASS non_empty_result
  - expected: `row_count > 0`
  - actual: `8`
- PASS expected_filter_fields
  - expected: `['DATE']`
  - actual: `['DATE']`

## PASS hbm_equipment_by_model

- PASS normalized_expected_intent_type
  - expected: `single_retrieval_analysis`
  - actual: `single_retrieval_analysis`
- PASS normalized_expected_analysis_kind
  - expected: `equipment_by_model`
  - actual: `equipment_by_model`
- PASS normalized_expected_datasets
  - expected: `['equipment_status']`
  - actual: `['equipment_status']`
- PASS expected_columns
  - expected: `['EQP_COUNT', 'EQP_MODEL', 'PRESS_CNT']`
  - actual: `['EQP_MODEL', 'EQP_COUNT', 'PRESS_CNT']`
- PASS non_empty_result
  - expected: `row_count > 0`
  - actual: `5`
- PASS expected_filter_fields
  - expected: `['PKG_TYPE1']`
  - actual: `['PKG_TYPE1']`
