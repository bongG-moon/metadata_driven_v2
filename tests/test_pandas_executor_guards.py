from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_component(path: str):
    component_path = ROOT / path
    spec = importlib.util.spec_from_file_location(component_path.stem, component_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_pandas_executor_drops_redundant_source_alias_columns_before_llm_code_runs() -> None:
    pandas_executor = load_component("langflow_components/main_flow/17_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "low_output_vs_target",
            "product_grain": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"],
            "production_column": "PRODUCTION",
            "target_column": "OUT_PLAN",
            "threshold": 1.0,
        },
        "state": {},
        "runtime_sources": {
            "production_data": [
                {
                    "TECH": "FC",
                    "DEN": "128G",
                    "MODE": "LPDDR5",
                    "PKG_TYPE1": "UFBGA",
                    "PKG_TYPE2": "MOBILE",
                    "LEAD": "LF",
                    "MCP_NO": "EMPTY",
                    "PRODUCTION": 10,
                }
            ],
            "target_data": [
                {
                    "TECH": "FC",
                    "DEN": "128G",
                    "Mode": "LPDDR5",
                    "MODE": "LPDDR5",
                    "PKG1": "UFBGA",
                    "PKG_TYPE1": "UFBGA",
                    "PKG2": "MOBILE",
                    "PKG_TYPE2": "MOBILE",
                    "LEAD": "LF",
                    "MCP NO": "EMPTY",
                    "MCP_NO": "EMPTY",
                    "OUT_PLAN": 20,
                }
            ],
        },
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "product_grain = plan['product_grain']",
                "production_df = sources['production_data'].copy()",
                "production_agg = production_df.groupby(product_grain, as_index=False)['PRODUCTION'].sum()",
                "target_df = sources['target_data'].copy()",
                "target_df = target_df.rename(columns={'Mode': 'MODE', 'PKG1': 'PKG_TYPE1', 'PKG2': 'PKG_TYPE2', 'MCP NO': 'MCP_NO'})",
                "target_agg = target_df.groupby(product_grain, as_index=False)['OUT_PLAN'].sum()",
                "target_agg = target_agg.rename(columns={'OUT_PLAN': 'TARGET_QTY'})",
                "result_df = production_agg.merge(target_agg, on=product_grain, how='outer')",
                "result_df['ACHIEVEMENT_RATE'] = result_df['PRODUCTION'].div(result_df['TARGET_QTY']).fillna(0)",
                "result_df['BALANCE'] = result_df['PRODUCTION'] - result_df['TARGET_QTY']",
                "result_df['LOW_OUTPUT_FLAG'] = result_df['ACHIEVEMENT_RATE'] < plan.get('threshold', 1.0)",
            ]
        ),
        "output_columns": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "PRODUCTION", "TARGET_QTY"],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["row_count"] == 1
    assert result["analysis"]["rows"][0]["TARGET_QTY"] == 20


def test_pandas_executor_normalizes_lot_process_column_alias() -> None:
    pandas_executor = load_component("langflow_components/main_flow/17_pandas_code_executor.py")
    payload = {
        "intent_plan": {"analysis_kind": "lot_count_by_process"},
        "state": {},
        "runtime_sources": {},
    }
    pandas_llm_json = {
        "code": "result_df = pd.DataFrame([{'OPER_NAME': 'D/A1', 'LOT_COUNT': 2}])",
        "output_columns": ["OPER_NAME", "LOT_COUNT"],
        "reasoning_steps": [],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["columns"] == ["OPER_SHORT_DESC", "LOT_COUNT"]
    assert result["analysis"]["rows"][0]["OPER_SHORT_DESC"] == "D/A1"


def test_pandas_executor_adds_missing_required_detail_columns() -> None:
    pandas_executor = load_component("langflow_components/main_flow/17_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "detail_rows",
            "retrieval_jobs": [
                {
                    "dataset_key": "lot_status",
                    "source_alias": "lot_data",
                    "required_columns": ["LOT_ID", "LOT_HOLD_STAT_CD", "HOLD_TM", "REASON_CD", "TECH_NM"],
                }
            ],
        },
        "state": {},
        "runtime_sources": {
            "lot_data": [
                {"LOT_ID": "LOT1", "LOT_HOLD_STAT_CD": "HOLD", "TECH": "FC"},
            ]
        },
    }
    pandas_llm_json = {
        "code": "result_df = sources['lot_data'][['LOT_ID', 'LOT_HOLD_STAT_CD', 'HOLD_TM', 'REASON_CD', 'TECH_NM']]",
        "output_columns": ["LOT_ID", "LOT_HOLD_STAT_CD", "HOLD_TM", "REASON_CD", "TECH_NM"],
        "reasoning_steps": [],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["columns"] == ["LOT_ID", "LOT_HOLD_STAT_CD", "HOLD_TM", "REASON_CD", "TECH_NM"]
    assert result["analysis"]["rows"][0]["HOLD_TM"] is None
    assert result["analysis"]["rows"][0]["TECH_NM"] is None


def test_pandas_executor_derives_rank_group_from_oper_name() -> None:
    pandas_executor = load_component("langflow_components/main_flow/17_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "rank_wip_then_join_production",
            "product_grain": ["TECH"],
        },
        "state": {},
        "runtime_sources": {},
    }
    pandas_llm_json = {
        "code": "result_df = pd.DataFrame([{'OPER_NAME': 'D/A1', 'WIP_RANK': 1, 'TECH': 'TSV', 'WIP': 10, 'PRODUCTION': 7}])",
        "output_columns": ["OPER_NAME", "WIP_RANK", "TECH", "WIP", "PRODUCTION"],
        "reasoning_steps": [],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["columns"][0] == "RANK_GROUP"
    assert result["analysis"]["rows"][0]["RANK_GROUP"] == "DA"


def test_pandas_executor_falls_back_for_lot_quantity_summary_to_frame_error() -> None:
    pandas_executor = load_component("langflow_components/main_flow/17_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "lot_quantity_summary",
            "step_plan": [{"source_alias": "lot_data"}],
        },
        "state": {},
        "runtime_sources": {
            "lot_data": [
                {"LOT_ID": "LOT1", "WF_QTY": 2, "SUB_PROD_QTY": 10},
                {"LOT_ID": "LOT1", "WF_QTY": 3, "SUB_PROD_QTY": 20},
                {"LOT_ID": "LOT2", "WF_QTY": 4, "SUB_PROD_QTY": 30},
            ]
        },
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "aggregated_data = sources['lot_data'].agg(",
                "    LOT_COUNT=('LOT_ID', 'nunique'),",
                "    WF_QTY=('WF_QTY', 'sum'),",
                "    DIE_QTY=('SUB_PROD_QTY', 'sum')",
                ")",
                "result_df = aggregated_data.to_frame().T",
            ]
        ),
        "output_columns": ["LOT_COUNT", "WF_QTY", "DIE_QTY"],
        "reasoning_steps": [],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["rows"][0] == {"LOT_COUNT": 2, "WF_QTY": 9, "DIE_QTY": 60}


def test_pandas_executor_falls_back_for_previous_source_aggregation() -> None:
    payload = {
        "intent_plan": {
            "analysis_kind": "aggregate_previous_source",
            "product_grain": ["MODE", "DEVICE"],
            "metric": "PRODUCTION",
            "step_plan": [
                {
                    "source_alias": "production_data",
                    "group_by": ["MODE", "DEVICE"],
                    "metric": "PRODUCTION",
                }
            ],
        },
        "state": {},
        "runtime_sources": {
            "production_data": [
                {"MODE": "LPDDR5", "DEVICE": "D1", "PRODUCTION": 10},
                {"MODE": "LPDDR5", "DEVICE": "D1", "PRODUCTION": 15},
                {"MODE": "LPDDR5", "DEVICE": "D2", "PRODUCTION": 20},
            ]
        },
    }
    pandas_llm_json = {
        "code": "result_df = missing_previous_source_df",
        "output_columns": ["MODE", "DEVICE", "PRODUCTION"],
        "reasoning_steps": [],
    }

    for executor_path in [
        "langflow_components/main_flow/17_pandas_code_executor.py",
        "langflow_components/data_analysis_flow/15_pandas_code_executor.py",
    ]:
        pandas_executor = load_component(executor_path)
        result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

        assert result["analysis"]["status"] == "ok"
        assert result["analysis"]["rows"] == [
            {"MODE": "LPDDR5", "DEVICE": "D1", "PRODUCTION": 25},
            {"MODE": "LPDDR5", "DEVICE": "D2", "PRODUCTION": 20},
        ]
