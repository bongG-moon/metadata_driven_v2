from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_metadata_loader_assembles_uploaded_mongodb_docs() -> None:
    module = _load_metadata_loader()

    metadata = module._assemble_metadata_from_mongo_docs(
        [
            {
                "_id": "domain:process_groups:DA",
                "section": "process_groups",
                "key": "DA",
                "payload": {"display_name": "D/A", "processes": ["D/A1"]},
            },
            {
                "_id": "domain:product_key_columns",
                "section": "product_key_columns",
                "key": "product_key_columns",
                "columns": ["TECH", "MODE"],
            },
        ],
        [
            {
                "_id": "table_catalog:production_today",
                "dataset_key": "production_today",
                "payload": {"source_type": "oracle", "columns": ["TECH", "MODE", "PRODUCTION"]},
            }
        ],
        [
            {
                "_id": "main_flow_filter:OPER_NAME",
                "filter_key": "OPER_NAME",
                "payload": {"column_candidates": ["OPER_NAME"]},
            }
        ],
    )

    assert metadata["domain_items"]["process_groups"]["DA"]["processes"] == ["D/A1"]
    assert metadata["domain_items"]["product_key_columns"] == ["TECH", "MODE"]
    assert metadata["table_catalog"]["datasets"]["production_today"]["source_type"] == "oracle"
    assert metadata["main_flow_filters"]["OPER_NAME"]["column_candidates"] == ["OPER_NAME"]


def test_metadata_loader_uses_local_fallback_when_auto_mongo_is_empty() -> None:
    module = _load_metadata_loader()

    payload = module.load_metadata_payload(
        {"request": {"question": "q"}, "warnings": []},
        mongo_uri="",
        metadata_source="auto",
        metadata_dir=str(ROOT / "metadata"),
        domain_collection_name="factory_domain_metadata",
        table_catalog_collection_name="factory_table_catalog_metadata",
        main_flow_filter_collection_name="factory_filter_metadata",
    )

    assert payload["metadata"]["domain_items"]["product_key_columns"]
    assert payload["metadata"]["table_catalog"]["datasets"]
    assert payload["metadata_context"]["metadata_load"]["source"] == "local_json"
    fallback = payload["metadata_context"]["metadata_load"]["fallback_from"]
    assert fallback["source"] == "mongodb"
    assert fallback["collections"] == {
        "domain_items": "factory_domain_metadata",
        "table_catalog": "factory_table_catalog_metadata",
        "main_flow_filters": "factory_filter_metadata",
    }


def _load_metadata_loader():
    path = ROOT / "langflow_components" / "main_flow" / "01_metadata_context_loader.py"
    spec = importlib.util.spec_from_file_location("metadata_context_loader", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
