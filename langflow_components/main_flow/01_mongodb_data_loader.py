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
    hydrate_mode: Any = "preview",
    preview_row_limit: Any = "5",
) -> dict[str, Any]:
    payload = _payload(payload_value)
    if not payload:
        return {"mongo_data_load": {"enabled": False, "loaded": False, "ref_count": 0, "errors": ["empty payload"]}}

    if not _truthy(enabled):
        return {**payload, "mongo_data_load": {"enabled": False, "loaded": False, "ref_count": 0, "errors": []}}

    uri = _clean(mongo_uri) or os.getenv("MONGODB_URI", "")
    database = _clean(mongo_database) or os.getenv("MONGODB_DATABASE", "metadata_driven_agent_v2")
    collection_name = _clean(result_collection_name) or os.getenv("MONGODB_RESULT_COLLECTION", DEFAULT_RESULT_COLLECTION)
    requested_mode = _hydrate_mode(hydrate_mode)
    mode = _resolve_hydrate_mode(requested_mode, payload)
    preview_limit = _positive_int(preview_row_limit, default=5, minimum=0)
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
    cache: dict[str, dict[str, Any]] = {}
    try:
        client, collection = _connect_collection(uri, database, collection_name)
        hydrated = _hydrate_refs(
            payload,
            collection,
            loaded,
            skipped,
            cache,
            path="",
            hydrate_mode=mode,
            preview_limit=preview_limit,
        )
        hydrated["mongo_data_load"] = {
            "enabled": True,
            "loaded": bool(loaded),
            "hydrate_mode": mode,
            "requested_hydrate_mode": requested_mode,
            "preview_row_limit": preview_limit,
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
    cache: dict[str, dict[str, Any]],
    path: str,
    hydrate_mode: str,
    preview_limit: int,
) -> Any:
    if isinstance(value, dict):
        if _metadata_only_path(path):
            return deepcopy(value)

        result = {
            key: _hydrate_refs(
                item,
                collection,
                loaded,
                skipped,
                cache,
                f"{path}.{key}" if path else key,
                hydrate_mode=hydrate_mode,
                preview_limit=preview_limit,
            )
            for key, item in value.items()
        }

        runtime_refs = result.get("runtime_source_refs") if isinstance(result.get("runtime_source_refs"), dict) else {}
        if runtime_refs:
            if hydrate_mode == "full":
                runtime_sources = result.get("runtime_sources") if isinstance(result.get("runtime_sources"), dict) else {}
                runtime_sources = deepcopy(runtime_sources)
                for alias, data_ref in runtime_refs.items():
                    if not _is_mongo_ref(data_ref):
                        continue
                    loaded_rows = _load_rows(collection, data_ref, cache, row_limit=None)
                    rows = loaded_rows["rows"]
                    if rows:
                        alias_text = str(alias)
                        runtime_sources[alias_text] = _json_ready(rows)
                        loaded.append(
                            {
                                "path": f"{path}.runtime_sources.{alias_text}" if path else f"runtime_sources.{alias_text}",
                                "ref_id": data_ref.get("ref_id"),
                                "row_count": len(rows),
                                "cache_hit": loaded_rows["cache_hit"],
                                "mode": "full",
                            }
                        )
                result["runtime_sources"] = runtime_sources
                result["runtime_sources_are_preview"] = False
            else:
                for alias, data_ref in runtime_refs.items():
                    if _is_mongo_ref(data_ref):
                        skipped.append(
                            {
                                "path": f"{path}.runtime_sources.{alias}" if path else f"runtime_sources.{alias}",
                                "ref_id": data_ref.get("ref_id"),
                                "reason": "preview_mode_runtime_source",
                            }
                        )

        data_ref = result.get("data_ref") if isinstance(result.get("data_ref"), dict) else {}
        if _is_mongo_ref(data_ref):
            if not _should_hydrate_ref(path):
                skipped.append({"path": path, "ref_id": data_ref.get("ref_id"), "reason": "metadata_only"})
                return result
            target_key = _row_target_key(result, path)
            if hydrate_mode != "full":
                existing_rows = result.get(target_key)
                if isinstance(existing_rows, list):
                    _mark_preview_ref(result, data_ref, existing_rows, target_key, preview_limit)
                    skipped.append({"path": path, "ref_id": data_ref.get("ref_id"), "reason": "preview_rows_already_present"})
                    return result
                loaded_rows = _load_rows(collection, data_ref, cache, row_limit=preview_limit)
                rows = loaded_rows["rows"]
                if rows or preview_limit == 0:
                    result[target_key] = _json_ready(rows)
                    result["row_count"] = int(data_ref.get("row_count") or loaded_rows.get("row_count") or len(rows))
                    result["columns"] = list(data_ref.get("columns") or loaded_rows.get("columns") or _rows_columns(rows))
                    result["data_ref_preview_loaded"] = True
                    result["data_ref_loaded"] = False
                    result["data_ref_load_mode"] = "preview"
                    result["data_is_preview"] = True
                    loaded.append(
                        {
                            "path": path,
                            "ref_id": data_ref.get("ref_id"),
                            "row_count": len(rows),
                            "cache_hit": loaded_rows["cache_hit"],
                            "mode": "preview",
                        }
                    )
                return result
            loaded_rows = _load_rows(collection, data_ref, cache, row_limit=None)
            rows = loaded_rows["rows"]
            if rows:
                result[target_key] = _json_ready(rows)
                result["row_count"] = len(rows)
                result["columns"] = list(data_ref.get("columns") or loaded_rows.get("columns") or _rows_columns(rows))
                result["data_ref_loaded"] = True
                result["data_ref_load_mode"] = "full"
                result["data_is_preview"] = False
                loaded.append(
                    {
                        "path": path,
                        "ref_id": data_ref.get("ref_id"),
                        "row_count": len(rows),
                        "cache_hit": loaded_rows["cache_hit"],
                        "mode": "full",
                    }
                )
        return result
    if isinstance(value, list):
        return [
            _hydrate_refs(
                item,
                collection,
                loaded,
                skipped,
                cache,
                f"{path}[{index}]",
                hydrate_mode=hydrate_mode,
                preview_limit=preview_limit,
            )
            for index, item in enumerate(value)
        ]
    return deepcopy(value)


def _load_rows(
    collection: Any,
    data_ref: dict[str, Any],
    cache: dict[str, dict[str, Any]],
    row_limit: int | None,
) -> dict[str, Any]:
    ref_id = str(data_ref.get("ref_id") or data_ref.get("id") or "").strip()
    if not ref_id:
        return {"rows": [], "cache_hit": False, "row_count": 0, "columns": []}
    cache_key = f"{ref_id}:full" if row_limit is None else f"{ref_id}:preview:{row_limit}"
    if cache_key in cache:
        cached = deepcopy(cache[cache_key])
        cached["cache_hit"] = True
        return cached
    doc = _find_ref_doc(collection, ref_id, row_limit)
    if not isinstance(doc, dict):
        return {"rows": [], "cache_hit": False, "row_count": 0, "columns": []}
    rows = doc.get("rows") if isinstance(doc.get("rows"), list) else doc.get("data")
    clean_rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    if row_limit is not None:
        clean_rows = clean_rows[:row_limit]
    row_count = int(doc.get("row_count") or data_ref.get("row_count") or len(clean_rows))
    columns = list(doc.get("columns") or data_ref.get("columns") or _rows_columns(clean_rows))
    result = {"rows": clean_rows, "cache_hit": False, "row_count": row_count, "columns": columns}
    cache[cache_key] = deepcopy(result)
    return result


def _find_ref_doc(collection: Any, ref_id: str, row_limit: int | None) -> dict[str, Any] | None:
    if row_limit is None:
        return collection.find_one({"ref_id": ref_id})
    projection = {
        "ref_id": 1,
        "row_count": 1,
        "columns": 1,
        "rows": {"$slice": row_limit},
        "data": {"$slice": row_limit},
    }
    try:
        return collection.find_one({"ref_id": ref_id}, projection)
    except TypeError:
        return collection.find_one({"ref_id": ref_id})


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


def _mark_preview_ref(result: dict[str, Any], data_ref: dict[str, Any], rows: list[Any], target_key: str, preview_limit: int) -> None:
    result["row_count"] = int(data_ref.get("row_count") or result.get("row_count") or len(rows))
    result["columns"] = list(data_ref.get("columns") or result.get("columns") or _rows_columns([row for row in rows if isinstance(row, dict)]))
    result["data_ref_loaded"] = False
    result["data_ref_load_mode"] = "preview"
    result["data_is_preview"] = bool(result.get("row_count", 0) > len(rows) or len(rows) >= preview_limit)
    result[target_key] = deepcopy(rows)


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


def _hydrate_mode(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"auto", "conditional"}:
        return "auto"
    if text in {"full", "all", "rows", "hydrate_full"}:
        return "full"
    return "preview"


def _resolve_hydrate_mode(mode: str, payload: dict[str, Any]) -> str:
    if mode != "auto":
        return mode
    return "full" if _requires_full_state_hydrate(payload) else "preview"


def _requires_full_state_hydrate(payload: dict[str, Any]) -> bool:
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    if _truthy(plan.get("requires_full_state_hydrate")):
        return True
    state_mode = str(plan.get("state_hydrate_mode") or "").strip().lower()
    return state_mode in {"full", "all", "rows", "hydrate_full"}


def _positive_int(value: Any, default: int, minimum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, parsed)


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
    display_name = "01 MongoDB Data Loader"
    description = "Restores MongoDB data_ref pointers as lightweight previews by default, or full rows when explicitly requested."
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
        MessageTextInput(name="hydrate_mode", display_name="Hydrate Mode", value="preview", advanced=True),
        MessageTextInput(name="preview_row_limit", display_name="Preview Row Limit", value="5", advanced=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        result = load_payload_from_mongodb(
            getattr(self, "payload", None),
            getattr(self, "mongo_uri", ""),
            getattr(self, "mongo_database", ""),
            getattr(self, "result_collection_name", ""),
            getattr(self, "enabled", "true"),
            getattr(self, "hydrate_mode", "preview"),
            getattr(self, "preview_row_limit", "5"),
        )
        meta = result.get("mongo_data_load", {}) if isinstance(result, dict) else {}
        self.status = {
            "loaded": meta.get("loaded", False),
            "hydrate_mode": meta.get("hydrate_mode"),
            "ref_count": meta.get("ref_count", 0),
            "errors": len(meta.get("errors", [])) if isinstance(meta.get("errors"), list) else 0,
        }
        return Data(data=result)
