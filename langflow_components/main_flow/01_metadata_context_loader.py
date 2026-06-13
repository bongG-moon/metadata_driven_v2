from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


CORE_DOMAIN_SECTIONS = {
    "process_groups",
    "product_terms",
    "quantity_terms",
    "metric_terms",
    "status_terms",
}


def load_metadata_payload(
    payload: dict[str, Any],
    mongo_uri: str = "",
    mongo_database: str = "",
    collection_prefix: str = "",
    metadata_source: str = "mongodb",
    metadata_dir: str = "",
    load_limit: str = "1000",
) -> dict[str, Any]:
    source_mode = _clean_text(metadata_source or os.getenv("METADATA_SOURCE") or "mongodb").lower()
    mongo_uri = _clean_text(mongo_uri or os.getenv("MONGODB_URI"))
    mongo_database = _clean_text(mongo_database or os.getenv("MONGODB_DATABASE") or "metadata_driven_agent_v2")
    collection_prefix = _clean_text(collection_prefix or os.getenv("MONGODB_COLLECTION_PREFIX") or "agent_v2")
    limit = _safe_int(load_limit, default=1000)

    metadata: dict[str, Any]
    load_info: dict[str, Any]
    if source_mode in {"mongodb", "mongo", "auto"}:
        metadata, load_info = load_metadata_from_mongodb(mongo_uri, mongo_database, collection_prefix, limit)
        if not load_info["errors"] and _metadata_has_core_items(metadata):
            return _attach_metadata(payload, metadata, load_info)
        if source_mode in {"mongodb", "mongo"} and not metadata_dir:
            return _attach_metadata(payload, metadata, load_info)

    if metadata_dir:
        metadata, local_info = load_metadata_from_local_files(metadata_dir)
        if source_mode in {"mongodb", "mongo", "auto"}:
            local_info["fallback_from"] = load_info
        return _attach_metadata(payload, metadata, local_info)

    empty_info = {
        "source": source_mode,
        "loaded_at": _now_iso(),
        "database": mongo_database,
        "collection_prefix": collection_prefix,
        "collections": {},
        "counts": _metadata_counts(_empty_metadata()),
        "errors": ["No MongoDB metadata was loaded and metadata_dir is empty."],
    }
    return _attach_metadata(payload, _empty_metadata(), empty_info)


def load_metadata_from_mongodb(
    mongo_uri: str,
    mongo_database: str,
    collection_prefix: str,
    limit: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    metadata = _empty_metadata()
    errors: list[str] = []
    docs_by_kind: dict[str, list[dict[str, Any]]] = {
        "domain_items": [],
        "table_catalog": [],
        "main_flow_filters": [],
    }
    collections = {
        "domain_items": f"{collection_prefix}_domain_items",
        "table_catalog": f"{collection_prefix}_table_catalog_items",
        "main_flow_filters": f"{collection_prefix}_main_flow_filters",
    }

    if not mongo_uri:
        errors.append("mongo_uri is empty. Set the input value or MONGODB_URI.")
    if not mongo_database:
        errors.append("mongo_database is empty. Set the input value or MONGODB_DATABASE.")
    if not collection_prefix:
        errors.append("collection_prefix is empty. Set the input value or MONGODB_COLLECTION_PREFIX.")
    if errors:
        return metadata, _load_info("mongodb", mongo_database, collection_prefix, collections, metadata, errors)

    client = None
    try:
        mongo_client_cls = getattr(import_module("pymongo"), "MongoClient")
        client = mongo_client_cls(mongo_uri, serverSelectionTimeoutMS=5000)
        db = client[mongo_database]
        for kind, collection_name in collections.items():
            cursor = db[collection_name].find({}).limit(limit)
            docs_by_kind[kind] = [_json_ready(dict(item)) for item in cursor]
    except Exception as exc:
        errors.append(str(exc))
    finally:
        if client is not None and hasattr(client, "close"):
            client.close()

    if not errors:
        metadata = _assemble_metadata_from_mongo_docs(
            docs_by_kind["domain_items"],
            docs_by_kind["table_catalog"],
            docs_by_kind["main_flow_filters"],
        )
    return metadata, _load_info("mongodb", mongo_database, collection_prefix, collections, metadata, errors, docs_by_kind)


def load_metadata_from_local_files(metadata_dir: str) -> tuple[dict[str, Any], dict[str, Any]]:
    metadata_path = Path(metadata_dir)
    errors: list[str] = []
    metadata = _empty_metadata()
    try:
        metadata = {
            "domain_items": _read_json(metadata_path / "domain_items.json"),
            "table_catalog": _read_json(metadata_path / "table_catalog.json"),
            "main_flow_filters": _read_json(metadata_path / "main_flow_filters.json"),
        }
    except Exception as exc:
        errors.append(str(exc))
    return metadata, {
        "source": "local_json",
        "loaded_at": _now_iso(),
        "metadata_dir": str(metadata_path),
        "collections": {},
        "counts": _metadata_counts(metadata),
        "errors": errors,
    }


def _assemble_metadata_from_mongo_docs(
    domain_docs: list[dict[str, Any]],
    table_docs: list[dict[str, Any]],
    filter_docs: list[dict[str, Any]],
) -> dict[str, Any]:
    metadata = _empty_metadata()

    for doc in domain_docs:
        if not _is_active_doc(doc):
            continue
        section = _clean_text(doc.get("section") or doc.get("gbn"))
        key = _clean_text(doc.get("key") or doc.get("name"))
        payload = deepcopy(doc.get("payload")) if isinstance(doc.get("payload"), dict) else {}
        if section == "product_key_columns":
            columns = doc.get("columns") or payload.get("columns") or payload.get("product_key_columns") or payload
            metadata["domain_items"]["product_key_columns"] = _as_string_list(columns)
        elif section in CORE_DOMAIN_SECTIONS and key:
            metadata["domain_items"].setdefault(section, {})[key] = payload

    for doc in table_docs:
        if not _is_active_doc(doc):
            continue
        dataset_key = _clean_text(doc.get("dataset_key") or doc.get("key"))
        payload = deepcopy(doc.get("payload")) if isinstance(doc.get("payload"), dict) else {}
        if dataset_key:
            metadata["table_catalog"]["datasets"][dataset_key] = payload

    for doc in filter_docs:
        if not _is_active_doc(doc):
            continue
        filter_key = _clean_text(doc.get("filter_key") or doc.get("key") or doc.get("parameter_key"))
        payload = deepcopy(doc.get("payload")) if isinstance(doc.get("payload"), dict) else {}
        if filter_key:
            metadata["main_flow_filters"][filter_key] = payload

    return metadata


def _attach_metadata(payload: dict[str, Any], metadata: dict[str, Any], load_info: dict[str, Any]) -> dict[str, Any]:
    next_payload = dict(payload or {})
    next_payload["metadata"] = metadata
    next_payload["metadata_context"] = {
        "domain_refs": [],
        "table_refs": [],
        "filter_refs": [],
        "metadata_load": _compact_load_info(load_info),
    }
    warnings = list(next_payload.get("warnings", [])) if isinstance(next_payload.get("warnings"), list) else []
    for error in load_info.get("errors", []):
        warnings.append(f"metadata_load: {error}")
    if warnings:
        next_payload["warnings"] = warnings
    return next_payload


def _empty_metadata() -> dict[str, Any]:
    return {
        "domain_items": {
            "process_groups": {},
            "product_terms": {},
            "quantity_terms": {},
            "metric_terms": {},
            "status_terms": {},
            "product_key_columns": [],
        },
        "table_catalog": {"datasets": {}},
        "main_flow_filters": {},
    }


def _metadata_has_core_items(metadata: dict[str, Any]) -> bool:
    domain = metadata.get("domain_items", {})
    table_catalog = metadata.get("table_catalog", {})
    return bool(domain.get("product_key_columns")) and bool(table_catalog.get("datasets"))


def _metadata_counts(metadata: dict[str, Any]) -> dict[str, int]:
    domain = metadata.get("domain_items", {}) if isinstance(metadata.get("domain_items"), dict) else {}
    return {
        "process_groups": len(domain.get("process_groups", {})),
        "product_terms": len(domain.get("product_terms", {})),
        "quantity_terms": len(domain.get("quantity_terms", {})),
        "metric_terms": len(domain.get("metric_terms", {})),
        "status_terms": len(domain.get("status_terms", {})),
        "product_key_columns": len(domain.get("product_key_columns", [])),
        "datasets": len((metadata.get("table_catalog", {}) or {}).get("datasets", {})),
        "main_flow_filters": len(metadata.get("main_flow_filters", {})),
    }


def _load_info(
    source: str,
    database: str,
    collection_prefix: str,
    collections: dict[str, str],
    metadata: dict[str, Any],
    errors: list[str],
    docs_by_kind: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    document_counts = {key: len(value) for key, value in (docs_by_kind or {}).items()}
    return {
        "source": source,
        "loaded_at": _now_iso(),
        "database": database,
        "collection_prefix": collection_prefix,
        "collections": collections,
        "document_counts": document_counts,
        "counts": _metadata_counts(metadata),
        "errors": errors,
    }


def _compact_load_info(load_info: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": load_info.get("source"),
        "loaded_at": load_info.get("loaded_at"),
        "database": load_info.get("database"),
        "collection_prefix": load_info.get("collection_prefix"),
        "collections": load_info.get("collections", {}),
        "document_counts": load_info.get("document_counts", {}),
        "counts": load_info.get("counts", {}),
        "errors": load_info.get("errors", []),
        "fallback_from": _compact_load_info(load_info["fallback_from"]) if isinstance(load_info.get("fallback_from"), dict) else None,
    }


def _is_active_doc(doc: dict[str, Any]) -> bool:
    status = _clean_text(doc.get("status")).lower()
    return not status or status in {"active", "enabled"}


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, dict):
        value = value.get("columns") or value.get("values") or []
    if not isinstance(value, list):
        value = [value]
    return [_clean_text(item) for item in value if _clean_text(item)]


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _safe_int(value: Any, default: int) -> int:
    try:
        return max(1, int(str(value or "").strip()))
    except Exception:
        return default


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_ready(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return str(value)


class MetadataContextLoader(Component):
    display_name = "01 Metadata Context Loader"
    description = "Loads domain, table catalog, and main-flow-filter metadata from MongoDB."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="mongo_uri", display_name="Mongo URI", value=""),
        MessageTextInput(name="mongo_database", display_name="Mongo Database", value="metadata_driven_agent_v2"),
        MessageTextInput(name="collection_prefix", display_name="Collection Prefix", value="agent_v2"),
        MessageTextInput(name="metadata_source", display_name="Metadata Source", value="mongodb", advanced=True),
        MessageTextInput(name="metadata_dir", display_name="Local Metadata Directory", value="", advanced=True),
        MessageTextInput(name="load_limit", display_name="Load Limit", value="1000", advanced=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        payload = getattr(self.payload, "data", self.payload)
        result = load_metadata_payload(
            payload,
            getattr(self, "mongo_uri", ""),
            getattr(self, "mongo_database", ""),
            getattr(self, "collection_prefix", ""),
            getattr(self, "metadata_source", "mongodb"),
            getattr(self, "metadata_dir", ""),
            getattr(self, "load_limit", "1000"),
        )
        load_info = result.get("metadata_context", {}).get("metadata_load", {})
        self.status = {
            "source": load_info.get("source"),
            "counts": load_info.get("counts", {}),
            "errors": len(load_info.get("errors", [])),
        }
        return Data(data=result)
