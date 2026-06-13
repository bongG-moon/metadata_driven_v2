from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timezone
from importlib import import_module
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import MessageTextInput, Output
from lfx.schema.data import Data


DOMAIN_SECTIONS = {
    "process_groups",
    "product_terms",
    "quantity_terms",
    "metric_terms",
    "status_terms",
    "product_key_columns",
}


def build_domain_authoring_request(
    raw_text: Any,
    mongo_uri: str = "",
    mongo_database: str = "",
    collection_prefix: str = "",
    collection_name: str = "",
    duplicate_action: str = "ask",
    load_existing: str = "true",
    load_limit: str = "200",
) -> dict[str, Any]:
    database = _clean(mongo_database or os.getenv("MONGODB_DATABASE") or "metadata_driven_agent_v2")
    prefix = _clean(collection_prefix or os.getenv("MONGODB_COLLECTION_PREFIX") or "agent_v2")
    collection = _clean(collection_name or f"{prefix}_domain_items")
    uri = _clean(mongo_uri or os.getenv("MONGODB_URI"))
    existing_items = []
    load_errors: list[str] = []
    if _as_bool(load_existing, True):
        existing_items, load_errors = _load_existing_domain_items(uri, database, collection, _safe_int(load_limit, 200))

    return {
        "metadata_type": "domain",
        "raw_text": _clean(raw_text),
        "refined_text": "",
        "items": [],
        "existing_items": existing_items,
        "existing_matches": [],
        "conflict_warnings": [],
        "duplicate_decision": {"action": _action(duplicate_action), "requires_user_choice": False},
        "review": {},
        "write_result": {},
        "mongo_config": {
            "database": database,
            "collection": collection,
            "collection_prefix": prefix,
            "has_mongo_uri": bool(uri),
        },
        "errors": [f"existing_load: {item}" for item in load_errors],
        "warnings": [],
        "trace": {"loaded_at": datetime.now(timezone.utc).isoformat()},
    }


def _load_existing_domain_items(
    mongo_uri: str,
    database: str,
    collection: str,
    limit: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not mongo_uri:
        return [], ["mongo_uri is empty, so existing domain metadata was not loaded."]
    client = None
    try:
        mongo_client_cls = getattr(import_module("pymongo"), "MongoClient")
        client = mongo_client_cls(mongo_uri, serverSelectionTimeoutMS=5000)
        docs = list(client[database][collection].find({}).limit(limit))
        return [_compact_domain_doc(_json_ready(doc)) for doc in docs if _is_active(doc)], []
    except Exception as exc:
        return [], [str(exc)]
    finally:
        if client is not None:
            client.close()


def _compact_domain_doc(doc: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(doc.get("payload")) if isinstance(doc.get("payload"), dict) else {}
    section = _clean(doc.get("section") or doc.get("gbn"))
    key = _clean(doc.get("key") or doc.get("name"))
    return {
        "id": _clean(doc.get("_id") or f"domain:{section}:{key}"),
        "section": section,
        "key": key,
        "aliases": _as_list(payload.get("aliases")),
        "processes": _as_list(payload.get("processes")),
        "columns": _as_list(doc.get("columns") or payload.get("columns") or payload.get("product_key_columns")),
        "payload_preview": {k: payload.get(k) for k in sorted(payload)[:8]},
    }


def _is_active(doc: dict[str, Any]) -> bool:
    status = _clean(doc.get("status")).lower()
    return not status or status in {"active", "enabled"}


def _json_ready(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return str(value)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    result = []
    for item in value:
        text = _clean(item)
        if text and text not in result:
            result.append(text)
    return result


def _safe_int(value: Any, default: int) -> int:
    try:
        return max(1, int(str(value or "").strip()))
    except Exception:
        return default


def _as_bool(value: Any, default: bool) -> bool:
    text = _clean(value).lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "y", "on"}


def _action(value: Any) -> str:
    action = _clean(value).lower()
    return action if action in {"ask", "merge", "replace", "skip", "create_new"} else "ask"


def _clean(value: Any) -> str:
    return str(value or "").strip()


class DomainAuthoringRequestLoader(Component):
    display_name = "00 Domain Authoring Request Loader"
    description = "Starts a domain metadata authoring request and optionally loads existing domain items from MongoDB."
    inputs = [
        MessageTextInput(name="raw_text", display_name="Natural Language Domain Description", required=True),
        MessageTextInput(name="mongo_uri", display_name="Mongo URI", value=""),
        MessageTextInput(name="mongo_database", display_name="Mongo Database", value="metadata_driven_agent_v2"),
        MessageTextInput(name="collection_prefix", display_name="Collection Prefix", value="agent_v2"),
        MessageTextInput(name="collection_name", display_name="Collection Name Override", value="", advanced=True),
        MessageTextInput(name="duplicate_action", display_name="Duplicate Action", value="ask", advanced=True),
        MessageTextInput(name="load_existing", display_name="Load Existing Items", value="true", advanced=True),
        MessageTextInput(name="load_limit", display_name="Load Limit", value="200", advanced=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        result = build_domain_authoring_request(
            getattr(self, "raw_text", ""),
            getattr(self, "mongo_uri", ""),
            getattr(self, "mongo_database", ""),
            getattr(self, "collection_prefix", ""),
            getattr(self, "collection_name", ""),
            getattr(self, "duplicate_action", "ask"),
            getattr(self, "load_existing", "true"),
            getattr(self, "load_limit", "200"),
        )
        self.status = {
            "metadata_type": "domain",
            "existing_items": len(result.get("existing_items", [])),
            "errors": len(result.get("errors", [])),
        }
        return Data(data=result)
