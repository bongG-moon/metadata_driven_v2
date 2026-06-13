from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "upload_json_to_mongodb.py"


def _load_upload_module():
    spec = importlib.util.spec_from_file_location("upload_json_to_mongodb", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_mongodb_upload_default_batches_include_only_core_metadata():
    module = _load_upload_module()
    batches = module.build_upload_batches(
        ROOT,
        domain_collection_name="factory_domain_metadata",
        table_catalog_collection_name="factory_table_catalog_metadata",
        main_flow_filter_collection_name="factory_filter_metadata",
    )

    assert list(batches) == [
        "factory_domain_metadata",
        "factory_table_catalog_metadata",
        "factory_filter_metadata",
    ]


def test_mongodb_upload_optional_batches_include_regression_and_samples():
    module = _load_upload_module()
    batches = module.build_upload_batches(
        ROOT,
        domain_collection_name="agent_v2_domain_items",
        table_catalog_collection_name="agent_v2_table_catalog_items",
        main_flow_filter_collection_name="agent_v2_main_flow_filters",
        include_regression=True,
        include_sample_data=True,
    )

    assert "agent_v2_regression_questions" in batches
    assert "agent_v2_sample_wip_today" in batches
    assert len(batches["agent_v2_regression_questions"]) >= 16


def test_mongodb_upload_docs_have_deterministic_ids():
    module = _load_upload_module()
    first = module.build_upload_batches(ROOT, collection_prefix="agent_v2", include_sample_data=True)
    second = module.build_upload_batches(ROOT, collection_prefix="agent_v2", include_sample_data=True)

    first_ids = [doc["_id"] for doc in first["agent_v2_sample_wip_today"]]
    second_ids = [doc["_id"] for doc in second["agent_v2_sample_wip_today"]]
    assert first_ids == second_ids


def test_mongodb_upload_keeps_legacy_prefix_for_old_callers():
    module = _load_upload_module()
    batches = module.build_upload_batches(ROOT, "agent_v2")

    assert list(batches) == [
        "agent_v2_domain_items",
        "agent_v2_table_catalog_items",
        "agent_v2_main_flow_filters",
    ]


def test_mongodb_upload_treats_single_custom_name_as_full_domain_collection():
    module = _load_upload_module()
    batches = module.build_upload_batches(ROOT, domain_collection_name="factory_domain_metadata")

    assert list(batches) == [
        "factory_domain_metadata",
        "agent_v2_table_catalog_items",
        "agent_v2_main_flow_filters",
    ]
