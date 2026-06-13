from __future__ import annotations

import json
import os
from copy import deepcopy
from importlib import import_module
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


DEFAULT_RESULT_COLLECTION = "agent_v2_result_store"


def load_payload_from_mongodb(
    payload_value: Any,
    mongo_uri: Any = "",
    mongo_database: Any = "",
    result_collection_name: Any = "",
    enabled: Any = "true",
) -> dict[str, Any]:
    payload = _payload(payload_value)
    if not payload:
        return {"mongo_data_load": {"enabled": False, "loaded": False, "ref_count": 0, "errors": ["empty payload"]}}

    if not _truthy(enabled):
        return {**payload, "mongo_data_load": {"enabled": False, "loaded": False, "ref_count": 0, "errors": []}}

    uri = _clean(mongo_uri) or os.getenv("MONGODB_URI", "")
    database = _clean(mongo_database) or os.getenv("MONGODB_DATABASE", "metadata_driven_agent_v2")
    collection_name = _clean(result_collection_name) or os.getenv("MONGODB_RESULT_COLLECTION", DEFAULT_RESULT_COLLECTION)
    missing = []
    if not uri:
        missing.append("Mongo URI is empty.")
    if not database:
        missing.append("Mongo database is empty.")
    if not collection_name:
        missing.append("Mongo result collection name is empty.")
    if missing:
        return {**payload, "mongo_data_load": {"enabled": True, "loaded": False, "ref_count": 0, "errors": missing}}

    client = None
    loaded: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    cache: dict[str, list[dict[str, Any]]] = {}
    try:
        client, collection = _connect_collection(uri, database, collection_name)
        hydrated = _hydrate_refs(payload, collection, loaded, skipped, cache, path="")
        hydrated["mongo_data_load"] = {
            "enabled": True,
            "loaded": bool(loaded),
            "ref_count": len(loaded),
            "unique_ref_count": len(cache),
            "loaded_refs": loaded,
            "skipped_refs": skipped,
            "result_collection_name": collection_name,
            "errors": [],
        }
        return hydrated
    except Exception as exc:
        return {**payload, "mongo_data_load": {"enabled": True, "loaded": False, "ref_count": 0, "errors": [str(exc)]}}
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def _hydrate_refs(
    value: Any,
    collection: Any,
    loaded: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    cache: dict[str, list[dict[str, Any]]],
    path: str,
) -> Any:
    if isinstance(value, dict):
        if _metadata_only_path(path):
            return deepcopy(value)

        result = {
            key: _hydrate_refs(item, collection, loaded, skipped, cache, f"{path}.{key}" if path else key)
            for key, item in value.items()
        }

        runtime_refs = result.get("runtime_source_refs") if isinstance(result.get("runtime_source_refs"), dict) else {}
        if runtime_refs:
            runtime_sources = result.get("runtime_sources") if isinstance(result.get("runtime_sources"), dict) else {}
            runtime_sources = deepcopy(runtime_sources)
            for alias, data_ref in runtime_refs.items():
                if not _is_mongo_ref(data_ref):
                    continue
                rows, cache_hit = _load_rows(collection, data_ref, cache)
                if rows:
                    alias_text = str(alias)
                    runtime_sources[alias_text] = _json_ready(rows)
                    loaded.append(
                        {
                            "path": f"{path}.runtime_sources.{alias_text}" if path else f"runtime_sources.{alias_text}",
                            "ref_id": data_ref.get("ref_id"),
                            "row_count": len(rows),
                            "cache_hit": cache_hit,
                        }
                    )
            result["runtime_sources"] = runtime_sources
            result["runtime_sources_are_preview"] = False

        data_ref = result.get("data_ref") if isinstance(result.get("data_ref"), dict) else {}
        if _is_mongo_ref(data_ref):
            if not _should_hydrate_ref(path):
                skipped.append({"path": path, "ref_id": data_ref.get("ref_id"), "reason": "metadata_only"})
                return result
            rows, cache_hit = _load_rows(collection, data_ref, cache)
            if rows:
                target_key = _row_target_key(result, path)
                result[target_key] = _json_ready(rows)
                result["row_count"] = len(rows)
                result["columns"] = list(data_ref.get("columns") or _rows_columns(rows))
                result["data_ref_loaded"] = True
                result["data_is_preview"] = False
                loaded.append({"path": path, "ref_id": data_ref.get("ref_id"), "row_count": len(rows), "cache_hit": cache_hit})
        return result
    if isinstance(value, list):
        return [_hydrate_refs(item, collection, loaded, skipped, cache, f"{path}[{index}]") for index, item in enumerate(value)]
    return deepcopy(value)


def _load_rows(collection: Any, data_ref: dict[str, Any], cache: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], bool]:
    ref_id = str(data_ref.get("ref_id") or data_ref.get("id") or "").strip()
    if not ref_id:
        return [], False
    if ref_id in cache:
        return deepcopy(cache[ref_id]), True
    doc = collection.find_one({"ref_id": ref_id})
    if not isinstance(doc, dict):
        return [], False
    rows = doc.get("rows") if isinstance(doc.get("rows"), list) else doc.get("data")
    clean_rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    cache[ref_id] = deepcopy(clean_rows)
    return clean_rows, False


def _connect_collection(mongo_uri: str, database: str, collection_name: str) -> tuple[Any, Any]:
    mongo_client_cls = getattr(import_module("pymongo"), "MongoClient")
    client = mongo_client_cls(mongo_uri, serverSelectionTimeoutMS=5000)
    return client, client[database][collection_name]


def _metadata_only_path(path: str) -> bool:
    normalized = f".{path.lower()}"
    return any(
        segment in normalized
        for segment in (
            ".data_refs",
            ".runtime_source_refs",
            ".source_results",
            ".followup_source_results",
            ".metadata_context",
            ".mongo_data_store",
            ".mongo_data_load",
        )
    )


def _should_hydrate_ref(path: str) -> bool:
    normalized = path.lower()
    return bool(
        normalized.endswith("data")
        or normalized.endswith("analysis")
        or normalized.endswith("current_data")
        or ".state.current_data" in normalized
    )


def _row_target_key(value: dict[str, Any], path: str) -> str:
    if isinstance(value.get("rows"), list):
        return "rows"
    if isinstance(value.get("data"), list):
        return "data"
    if path.lower().endswith("data") or path.lower().endswith("current_data"):
        return "rows"
    return "data"


def _is_mongo_ref(value: Any) -> bool:
    return isinstance(value, dict) and value.get("store") == "mongodb" and bool(value.get("ref_id"))


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        return deepcopy(data)
    text = getattr(value, "text", None) or getattr(value, "content", None)
    if isinstance(text, str):
        try:
            parsed = json.loads(text)
        except Exception:
            return {"text": text}
        return parsed if isinstance(parsed, dict) else {"text": text}
    return {}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() not in {"", "0", "false", "no", "off", "none", "null"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _json_ready(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return str(value)


def _rows_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in row:
            text = str(key)
            if text not in columns:
                columns.append(text)
    return columns


class MongoDBDataLoader(Component):
    display_name = "06 MongoDB Data Loader"
    description = "Hydrates MongoDB data_ref pointers back to rows before pandas analysis or follow-up planning."
    icon = "DatabaseZap"
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="mongo_uri", display_name="Mongo URI", value="", advanced=True),
        MessageTextInput(name="mongo_database", display_name="Mongo Database", value="", advanced=True),
        MessageTextInput(
            name="result_collection_name",
            display_name="Result Collection Full Name",
            value=DEFAULT_RESULT_COLLECTION,
            advanced=True,
        ),
        MessageTextInput(name="enabled", display_name="Enabled", value="true", advanced=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        result = load_payload_from_mongodb(
            getattr(self, "payload", None),
            getattr(self, "mongo_uri", ""),
            getattr(self, "mongo_database", ""),
            getattr(self, "result_collection_name", ""),
            getattr(self, "enabled", "true"),
        )
        meta = result.get("mongo_data_load", {}) if isinstance(result, dict) else {}
        self.status = {
            "loaded": meta.get("loaded", False),
            "ref_count": meta.get("ref_count", 0),
            "errors": len(meta.get("errors", [])) if isinstance(meta.get("errors"), list) else 0,
        }
        return Data(data=result)
