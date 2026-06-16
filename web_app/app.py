from __future__ import annotations

import html
import uuid
from typing import Any

import pandas as pd
import streamlit as st

from .langflow_client import LangflowApiClient, LangflowSettings
from .mock_api import MockApiClient
from .ui_helpers import chat_dataframe_height, compact_json_html, display_table_frame, json_text, safe_markdown_text


APP_TITLE = "Metadata Agent Console"
PAGE_QUERY = "질의/분석"
PAGE_AUTHORING = "Metadata 등록"
PAGE_LOOKUP = "Metadata 조회"
PAGE_VALIDATE = "등록 후 검증"
NAV_PAGES = [PAGE_QUERY, PAGE_AUTHORING, PAGE_LOOKUP, PAGE_VALIDATE]

AUTHORING_TYPES = {
    "domain": "Domain",
    "table_catalog": "Table catalog",
    "main_flow_filter": "Main flow filter",
}
ACTION_LABELS = {
    "ask": "먼저 확인",
    "merge": "기존 내용 보강",
    "replace": "기존 내용 교체",
    "skip": "저장하지 않음",
    "create_new": "새 key로 등록",
}
QUERY_EXAMPLES = [
    "오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아주고 해당 제품들의 오늘 생산량도 보여줘",
    "현재 da에서 재공이 가장 많은 제품 알려줘",
    "이 제품에 할당된 장비 현황 알려줘",
    "오늘 DA공정에서 재공, 생산량과 목표값 그리고 생산달성율을 보여줘",
    "현재 조회 가능한 DATA LIST 알려줘",
    "production_today 조회 쿼리문 알려줘",
]
AUTHORING_EXAMPLES = {
    "domain": "W/B공정은 W/B1부터 W/B6까지야. 재공 수량은 WIP 컬럼을 합산해.",
    "table_catalog": "wip_today는 Oracle PNT_RPT에서 SELECT WORK_DT, OPER_NAME, WIP FROM PKG_WIP_TODAY WHERE WORK_DT = {DATE}로 조회해. DATE는 WORK_DT에 매핑해.",
    "main_flow_filter": "날짜 조건은 DATE라는 기준 필터로 사용해줘. 오늘, 금일, 작업일은 WORK_DT 후보 컬럼과 연결해.",
}


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    inject_style()
    ensure_state()
    settings = render_sidebar()
    if settings["page"] == PAGE_QUERY:
        render_query_page(settings)
    elif settings["page"] == PAGE_AUTHORING:
        render_authoring_page(settings)
    elif settings["page"] == PAGE_LOOKUP:
        render_lookup_page(settings)
    else:
        render_validation_page(settings)


def ensure_state() -> None:
    if "mock_api" not in st.session_state:
        st.session_state.mock_api = MockApiClient()
    if "langflow_api" not in st.session_state:
        st.session_state.langflow_api = LangflowApiClient()
    if "session_id" not in st.session_state:
        st.session_state.session_id = f"web-{uuid.uuid4().hex[:8]}"
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "latest_state" not in st.session_state:
        st.session_state.latest_state = {}
    if "authoring_results" not in st.session_state:
        st.session_state.authoring_results = []


def render_sidebar() -> dict[str, Any]:
    api_settings = LangflowSettings.from_env()
    if getattr(st.session_state.langflow_api, "settings", None) != api_settings:
        st.session_state.langflow_api = LangflowApiClient(api_settings)
    configured = api_settings.configured_summary()
    api_ready = configured["main"]
    st.sidebar.markdown(
        """
        <div class="sidebar-brand">
          <div class="sidebar-brand-row">
            <div class="sidebar-brand-mark">M2</div>
            <div>
              <div class="sidebar-brand-title">Metadata Agent</div>
              <div class="sidebar-brand-subtitle">Langflow-ready web console</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    page = st.sidebar.radio("Navigation", NAV_PAGES, label_visibility="collapsed", key="nav_page")
    st.sidebar.markdown('<div class="sidebar-section-label">Runtime</div>', unsafe_allow_html=True)
    runtime_mode = st.sidebar.radio(
        "Runtime mode",
        ["Python mock", "Langflow API"],
        index=0,
        label_visibility="collapsed",
        key="runtime_mode",
    )
    st.sidebar.markdown(
        f"""
        <div class="config-list">
          <div class="config-row">
            <div><div class="config-label">Selected</div><div class="config-env">{html.escape(runtime_mode)}</div></div>
            <span class="config-badge {'ok' if runtime_mode == 'Python mock' or api_ready else 'warn'}">{'Ready' if runtime_mode == 'Langflow API' and api_ready else 'Mock' if runtime_mode == 'Python mock' else 'Missing'}</span>
          </div>
          <div class="config-row">
            <div><div class="config-label">Query APIs</div><div class="config-env">ROUTER_FLOW_ID / MAIN_FLOW_ID</div></div>
            <span class="config-badge {'ok' if configured['main'] else 'warn'}">{'set' if configured['main'] else 'empty'}</span>
          </div>
          <div class="config-row">
            <div><div class="config-label">Authoring APIs</div><div class="config-env">domain/table/filter</div></div>
            <span class="config-value">{sum(1 for key in ('domain', 'table_catalog', 'main_flow_filter') if configured.get(key))}/3</span>
          </div>
          <div class="config-row">
            <div><div class="config-label">Result store</div><div class="config-env">MONGODB_RESULT_COLLECTION</div></div>
            <span class="config-value">agent_v2_result_store</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if runtime_mode == "Langflow API" and not api_ready:
        st.sidebar.warning("Query Langflow API URL 또는 flow id가 없어 질의를 실행할 수 없습니다. env 설정 전에는 Python mock을 사용하세요.")
    developer_mode = st.sidebar.toggle("개발자 정보 보기", value=True)
    number_mode = st.sidebar.selectbox("숫자 표시", ["comma", "k"], format_func=lambda item: "1,000" if item == "comma" else "1.0K")
    if st.sidebar.button("세션 초기화", width="stretch"):
        st.session_state.session_id = f"web-{uuid.uuid4().hex[:8]}"
        st.session_state.chat_messages = []
        st.session_state.latest_state = {}
        st.rerun()
    return {
        "page": page,
        "developer_mode": developer_mode,
        "number_mode": number_mode,
        "runtime_mode": runtime_mode,
        "api_ready": api_ready,
        "api_settings": api_settings,
    }


def render_query_page(settings: dict[str, Any]) -> None:
    render_topbar("질의/분석", st.session_state.session_id)
    if settings.get("runtime_mode") == "Langflow API":
        st.caption("Langflow Run API 응답을 현재 웹 표준 shape로 정규화해서 표시합니다.")
    else:
        st.caption("Python mock API가 reference runtime을 호출합니다. 후속 질문 state와 data_ref 동작까지 화면에서 확인할 수 있습니다.")

    example_cols = st.columns(len(QUERY_EXAMPLES))
    for index, question in enumerate(QUERY_EXAMPLES):
        if example_cols[index].button(f"예시 {index + 1}", key=f"query_example_{index}", width="stretch"):
            st.session_state.pending_question = question

    for index, message in enumerate(st.session_state.chat_messages):
        with st.chat_message(message["role"], avatar=":material/person:" if message["role"] == "user" else ":material/smart_toy:"):
            if message["role"] == "assistant":
                render_query_result(message["result"], settings, f"history_{index}")
            else:
                st.markdown(safe_markdown_text(message["content"]))

    pending = st.session_state.pop("pending_question", None)
    user_message = st.chat_input("제조 데이터 질문을 입력하세요")
    if pending and not user_message:
        user_message = pending
    if not user_message:
        return

    st.session_state.chat_messages.append({"role": "user", "content": user_message})
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(safe_markdown_text(user_message))
    with st.chat_message("assistant", avatar=":material/smart_toy:"):
        with st.spinner("Langflow API 실행 중..." if settings.get("runtime_mode") == "Langflow API" else "Python mock API 실행 중..."):
            result = run_query_backend(user_message, settings)
            st.session_state.latest_state = result.get("state", {})
        render_query_result(result, settings, "latest")
    st.session_state.chat_messages.append({"role": "assistant", "content": result.get("answer_message", ""), "result": result})


def run_query_backend(user_message: str, settings: dict[str, Any]) -> dict[str, Any]:
    try:
        if settings.get("runtime_mode") == "Langflow API":
            return st.session_state.langflow_api.run_query(
                user_message,
                session_id=st.session_state.session_id,
                state=st.session_state.latest_state or None,
            )
        return st.session_state.mock_api.run_query(
            user_message,
            session_id=st.session_state.session_id,
            state=st.session_state.latest_state or None,
        )
    except Exception as exc:
        return {
            "status": "error",
            "success": False,
            "answer_message": f"실행 중 오류가 발생했습니다: {exc}",
            "data": {"columns": [], "rows": [], "row_count": 0, "data_ref": {}},
            "applied_scope": {},
            "intent_plan": {},
            "analysis": {"status": "error", "errors": [str(exc)]},
            "state": st.session_state.latest_state or {},
            "warnings": [],
            "errors": [str(exc)],
            "api_mode": settings.get("runtime_mode", "unknown"),
        }


def render_query_result(result: dict[str, Any], settings: dict[str, Any], key_prefix: str) -> None:
    st.markdown(safe_markdown_text(result.get("answer_message") or "응답 메시지가 없습니다."))
    is_metadata_qa = bool(result.get("direct_response_ready") or result.get("response_type") == "metadata_qa" or result.get("metadata_qa"))
    metadata_qa = result.get("metadata_qa") if isinstance(result.get("metadata_qa"), dict) else {}
    if is_metadata_qa:
        render_inline_status("Metadata QA", metadata_qa_label(metadata_qa), "success")
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    rows = data.get("rows") if isinstance(data.get("rows"), list) else []
    columns = data.get("columns") if isinstance(data.get("columns"), list) else []
    row_count = int(data.get("row_count") or len(rows) or 0)
    metric_cols = st.columns(4)
    metric_cols[0].metric("Rows", f"{row_count:,}")
    metric_cols[1].metric("Preview", f"{len(rows):,}")
    metric_cols[2].metric("Datasets", f"{len((result.get('applied_scope') or {}).get('datasets') or []):,}")
    metric_cols[3].metric("Status", str(result.get("status") or "ok"))
    if rows:
        frame = pd.DataFrame(rows)
        if columns:
            ordered = [column for column in columns if column in frame.columns]
            frame = frame[ordered + [column for column in frame.columns if column not in ordered]]
        st.dataframe(
            display_table_frame(frame, settings.get("number_mode", "comma")),
            hide_index=True,
            width="stretch",
            height=chat_dataframe_height(row_count),
        )
    else:
        render_inline_status("결과", "표시할 row가 없습니다.", "warning")

    data_ref = data.get("data_ref") if isinstance(data.get("data_ref"), dict) else {}
    if data_ref:
        with st.expander("전체 row data_ref", expanded=False):
            render_compact_json(data_ref)
            if result.get("api_mode") == "python_mock" or settings.get("runtime_mode") == "Python mock":
                full_rows = st.session_state.mock_api.get_rows(data_ref)
                st.download_button(
                    "전체 row JSON 다운로드",
                    data=json_text(full_rows),
                    file_name=f"{data_ref.get('ref_id', 'rows')}.json",
                    mime="application/json",
                    key=f"{key_prefix}_download_rows",
                    width="stretch",
                )
            else:
                render_inline_status("전체 row", "Langflow API 모드에서는 backend가 이 data_ref로 MongoDB result store를 조회합니다.")
                st.download_button(
                    "data_ref JSON 다운로드",
                    data=json_text(data_ref),
                    file_name=f"{data_ref.get('ref_id', 'data_ref')}.json",
                    mime="application/json",
                    key=f"{key_prefix}_download_ref",
                    width="stretch",
                )
    if is_metadata_qa:
        tabs = st.tabs(["Metadata QA", "적용 Scope", "Intent", "Raw"])
        with tabs[0]:
            render_compact_json(
                {
                    "metadata_qa": metadata_qa,
                    "metadata_route": result.get("metadata_route") or {},
                    "analysis": {key: value for key, value in (result.get("analysis") or {}).items() if key != "rows"},
                },
                max_height=360,
            )
        with tabs[1]:
            render_compact_json(result.get("applied_scope") or {})
        with tabs[2]:
            render_compact_json(result.get("intent_plan") or result.get("intent") or {})
        with tabs[3]:
            render_raw_result(result, settings)
    else:
        tabs = st.tabs(["적용 Scope", "Intent", "Pandas", "Raw"])
        with tabs[0]:
            render_compact_json(result.get("applied_scope") or {})
        with tabs[1]:
            render_compact_json(result.get("intent_plan") or result.get("intent") or {})
        with tabs[2]:
            analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
            code = analysis.get("analysis_code") or (analysis.get("pandas_code_json") or {}).get("code", "")
            if code:
                st.code(str(code), language="python")
            render_compact_json({key: value for key, value in analysis.items() if key not in {"rows", "analysis_code", "pandas_code_json"}})
        with tabs[3]:
            render_raw_result(result, settings)


def metadata_qa_label(metadata_qa: dict[str, Any]) -> str:
    action = str(metadata_qa.get("metadata_action") or "direct_answer")
    target = metadata_qa.get("target_dataset") or metadata_qa.get("target_family") or metadata_qa.get("target_term")
    if target:
        return f"{action} · {target}"
    return action


def render_raw_result(result: dict[str, Any], settings: dict[str, Any]) -> None:
    if settings.get("developer_mode"):
        render_compact_json(result, max_height=520)
    else:
        render_inline_status("개발자 정보", "사이드바에서 개발자 정보 보기를 켜면 Raw payload를 볼 수 있습니다.")


def render_authoring_page(settings: dict[str, Any]) -> None:
    render_topbar("Metadata 등록", st.session_state.session_id)
    flow_key = st.segmented_control("등록 유형", list(AUTHORING_TYPES), format_func=lambda key: AUTHORING_TYPES[key], default="domain")
    action = st.selectbox("저장 방식", list(ACTION_LABELS), format_func=lambda key: ACTION_LABELS[key], index=0)
    text = st.text_area("자연어 설명", value=AUTHORING_EXAMPLES[flow_key], height=180)
    run_col, clear_col = st.columns([1, 4])
    run_clicked = run_col.button("Langflow 실행" if settings.get("runtime_mode") == "Langflow API" else "Mock 실행", type="primary", width="stretch")
    if clear_col.button("결과 지우기", width="stretch"):
        st.session_state.authoring_results = []
        st.rerun()
    if run_clicked:
        with st.spinner("Langflow authoring API 실행 중..." if settings.get("runtime_mode") == "Langflow API" else "Python mock authoring 실행 중..."):
            result = run_authoring_backend(flow_key, text, action, settings)
        st.session_state.authoring_results.insert(0, result)
    if not st.session_state.authoring_results:
        render_inline_status("대기", "실행하면 정제 텍스트, 생성 item, 검토, 저장 결과가 표시됩니다.")
        return
    for index, result in enumerate(st.session_state.authoring_results[:5]):
        with st.container(border=False):
            render_authoring_result(result, f"authoring_{index}")


def run_authoring_backend(flow_key: str, text: str, action: str, settings: dict[str, Any]) -> dict[str, Any]:
    try:
        if settings.get("runtime_mode") == "Langflow API":
            return st.session_state.langflow_api.run_authoring(flow_key, text, action, st.session_state.session_id)
        return st.session_state.mock_api.run_authoring(flow_key, text, action, st.session_state.session_id)
    except Exception as exc:
        return {
            "status": "error",
            "ui_status": "error",
            "message": f"실행 중 오류가 발생했습니다: {exc}",
            "metadata_type": flow_key,
            "items": [],
            "existing_matches": [],
            "conflict_warnings": [],
            "review": {},
            "write_result": {"status": "error", "errors": [str(exc)]},
            "trace": {"raw_text": text, "duplicate_decision": {"action": action}},
            "errors": [str(exc)],
            "warnings": [],
            "api_mode": settings.get("runtime_mode", "unknown"),
        }


def render_authoring_result(result: dict[str, Any], key_prefix: str) -> None:
    ui_status = result.get("ui_status") or result.get("status")
    tone = "success" if ui_status == "saved" else "warning" if ui_status in {"needs_more_input", "duplicate_choice_required", "warning"} else "error"
    render_inline_status(str(ui_status), result.get("message", ""), tone)
    tabs = st.tabs(["생성 item", "부족/중복", "검토/저장", "Trace"])
    with tabs[0]:
        items = result.get("items") if isinstance(result.get("items"), list) else []
        if items:
            st.dataframe(pd.DataFrame([flatten_item(item) for item in items]), hide_index=True, width="stretch")
            render_compact_json(items, max_height=320)
        else:
            render_inline_status("items", "생성된 item이 없습니다.", "warning")
    with tabs[1]:
        render_detail_list("부족한 정보", (result.get("review") or {}).get("supplement_requests") or [])
        render_detail_list("비슷한 기존 정보", result.get("existing_matches") or [])
        render_detail_list("경고", result.get("conflict_warnings") or [])
    with tabs[2]:
        render_compact_json({"review": result.get("review"), "write_result": result.get("write_result")}, max_height=360)
    with tabs[3]:
        render_compact_json(result.get("trace") or {}, max_height=300)
        if result.get("pending_authoring_id"):
            st.code(str(result["pending_authoring_id"]))


def render_lookup_page(settings: dict[str, Any]) -> None:
    render_topbar("Metadata 조회", st.session_state.session_id)
    flow_key = st.segmented_control("Metadata type", list(AUTHORING_TYPES), format_func=lambda key: AUTHORING_TYPES[key], default="domain", key="lookup_type")
    keyword = st.text_input("검색어", placeholder="key, alias, source type 검색")
    rows = st.session_state.mock_api.list_metadata(flow_key)
    if keyword:
        needle = keyword.lower()
        rows = [row for row in rows if needle in json_text(row).lower()]
    st.caption(f"{len(rows):,}개 metadata item")
    if rows:
        frame = pd.DataFrame([lookup_row(row, flow_key) for row in rows])
        st.dataframe(frame, hide_index=True, width="stretch", height=chat_dataframe_height(len(frame), 520))
        selected = st.selectbox("상세 보기", [lookup_label(row, flow_key) for row in rows])
        selected_row = rows[[lookup_label(row, flow_key) for row in rows].index(selected)]
        render_compact_json(selected_row, max_height=460)
    else:
        render_inline_status("검색", "조건에 맞는 metadata가 없습니다.", "warning")


def render_validation_page(settings: dict[str, Any]) -> None:
    render_topbar("등록 후 검증", st.session_state.session_id)
    questions = st.session_state.mock_api.validation_questions()
    labels = [f"{item['id']} - {item['question']}" for item in questions]
    selected = st.selectbox("검증 질문", labels)
    item = questions[labels.index(selected)]
    st.text_area("질문", value=item["question"], height=90, key="validation_question")
    if st.button("Langflow 검증 실행" if settings.get("runtime_mode") == "Langflow API" else "Mock 검증 실행", type="primary"):
        validation = run_validation_backend(st.session_state.validation_question, item.get("expected_datasets"), settings)
        st.session_state.validation_result = validation
    validation = st.session_state.get("validation_result")
    if not validation:
        render_inline_status("대기", "검증을 실행하면 기대 dataset과 실제 적용 결과를 비교합니다.")
        return
    tone = "success" if validation["passed"] else "error"
    render_inline_status("검증 결과", "통과" if validation["passed"] else "확인 필요", tone)
    cols = st.columns(2)
    cols[0].markdown("#### 기대 dataset")
    cols[0].write(validation["expected_datasets"])
    cols[1].markdown("#### 실제 dataset")
    cols[1].write(validation["actual_datasets"])
    render_query_result(validation["result"], settings, "validation")


def run_validation_backend(question: str, expected_datasets: list[str] | None, settings: dict[str, Any]) -> dict[str, Any]:
    if settings.get("runtime_mode") != "Langflow API":
        return st.session_state.mock_api.validate_question(
            question,
            expected_datasets=expected_datasets,
            session_id="validation-session",
        )
    result = run_query_backend(question, {"runtime_mode": "Langflow API", **settings})
    actual = set((result.get("applied_scope") or {}).get("datasets") or [])
    expected = set(expected_datasets or [])
    return {
        "passed": expected.issubset(actual) if expected else bool(result.get("answer_message")),
        "expected_datasets": sorted(expected),
        "actual_datasets": sorted(actual),
        "result": result,
    }


def render_topbar(title: str, session_id: str) -> None:
    safe_title = html.escape(title)
    safe_session = html.escape(str(session_id))
    st.markdown(
        f"""
        <div class="chat-topbar">
          <div class="chat-topbar-title">{safe_title}</div>
          <div class="session-strip">
            <div class="session-strip-label">Session ID</div>
            <div class="session-strip-value">{safe_session}</div>
          </div>
        </div>
        <div class="chat-topbar-spacer"></div>
        """,
        unsafe_allow_html=True,
    )


def render_inline_status(label: str, value: Any, tone: str = "info") -> None:
    safe_label = html.escape(str(label or ""))
    safe_value = html.escape(str(value or ""))
    st.markdown(f'<div class="inline-status inline-status-{tone}"><b>{safe_label}</b><span>{safe_value}</span></div>', unsafe_allow_html=True)


def render_compact_json(value: Any, max_height: int | None = None) -> None:
    style = f' style="max-height:{int(max_height)}px; overflow:auto;"' if max_height else ""
    st.html(f'<pre class="compact-json-block"{style}>{compact_json_html(value)}</pre>')


def render_detail_list(title: str, values: list[Any]) -> None:
    st.markdown(f"#### {title}")
    if not values:
        render_inline_status(title, "표시할 항목이 없습니다.")
        return
    for value in values:
        render_compact_json(value, max_height=180)


def flatten_item(item: dict[str, Any]) -> dict[str, Any]:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    return {
        "section": item.get("section", ""),
        "key": item.get("key") or item.get("dataset_key") or item.get("filter_key") or "",
        "status": item.get("status", ""),
        "display_name": payload.get("display_name", ""),
        "aliases": ", ".join(str(alias) for alias in payload.get("aliases", [])[:5]) if isinstance(payload.get("aliases"), list) else "",
    }


def lookup_row(row: dict[str, Any], flow_key: str) -> dict[str, Any]:
    if flow_key == "domain":
        return {
            "section": row.get("section"),
            "key": row.get("key"),
            "display_name": row.get("display_name"),
            "aliases": ", ".join(row.get("aliases", [])[:5]),
            "status": row.get("status"),
        }
    if flow_key == "table_catalog":
        return {
            "dataset_key": row.get("dataset_key"),
            "display_name": row.get("display_name"),
            "dataset_family": row.get("dataset_family"),
            "source_type": row.get("source_type"),
            "status": row.get("status"),
        }
    return {
        "filter_key": row.get("filter_key"),
        "display_name": row.get("display_name"),
        "semantic_role": row.get("semantic_role"),
        "column_candidates": ", ".join(row.get("column_candidates", [])[:4]),
        "status": row.get("status"),
    }


def lookup_label(row: dict[str, Any], flow_key: str) -> str:
    if flow_key == "domain":
        return f"{row.get('section')}/{row.get('key')}"
    if flow_key == "table_catalog":
        return str(row.get("dataset_key"))
    return str(row.get("filter_key"))


def inject_style() -> None:
    st.markdown(
        """
        <style>
        :root {
            --blue: #2563eb;
            --blue-dark: #1d4ed8;
            --ink: #101828;
            --muted: #667085;
            --line: #d7dde8;
            --surface: #ffffff;
            --soft: #f6f8fb;
            --green: #0f766e;
            --amber: #b45309;
            --red: #b42318;
        }
        .block-container { padding-top: 1.05rem; padding-bottom: 3rem; max-width: 1280px; }
        [data-testid="stAppViewContainer"] { background: #fbfcfe; color: var(--ink); }
        [data-testid="stSidebar"] { background: #f5f7fb; border-right: 1px solid var(--line); }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { font-size: 0.78rem; }
        .sidebar-brand { border-bottom: 1px solid var(--line); padding: 0.45rem 0 0.9rem; margin-bottom: 0.75rem; }
        .sidebar-brand-row { display: flex; align-items: center; gap: 0.7rem; }
        .sidebar-brand-mark {
            width: 2.15rem; height: 2.15rem; border-radius: 0.45rem;
            display: grid; place-items: center; color: #fff; background: var(--blue);
            font-weight: 800; font-size: 0.82rem;
        }
        .sidebar-brand-title { color: var(--ink); font-weight: 800; letter-spacing: 0; font-size: 0.98rem; }
        .sidebar-brand-subtitle { color: var(--muted); font-size: 0.72rem; margin-top: 0.06rem; }
        .sidebar-section-label { color: #475467; font-size: 0.68rem; font-weight: 800; text-transform: uppercase; margin: 1rem 0 0.35rem; }
        div[role="radiogroup"] label { min-height: 2rem; border-radius: 0.45rem; padding: 0.1rem 0.32rem; }
        div[role="radiogroup"] label:has(input:checked) { background: #eaf1ff; color: var(--blue-dark); }
        .config-list { display: grid; gap: 0.42rem; }
        .config-row {
            display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0.6rem; align-items: center;
            border: 1px solid var(--line); background: var(--surface); border-radius: 0.45rem; padding: 0.55rem 0.62rem;
        }
        .config-label { color: #344054; font-size: 0.72rem; font-weight: 750; }
        .config-env { color: var(--muted); font-size: 0.64rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .config-badge { display: inline-flex; align-items: center; justify-content: center; min-height: 1.35rem; padding: 0 0.48rem; border-radius: 0.35rem; font-size: 0.66rem; font-weight: 750; }
        .config-badge.ok { background: #dff7ef; color: #047857; }
        .config-badge.warn { background: #fff7ed; color: #b45309; }
        .config-value { color: #475467; font-size: 0.68rem; }
        .chat-topbar {
            position: sticky; top: 0; z-index: 20; min-height: 2.7rem;
            display: flex; align-items: center; justify-content: space-between; gap: 1rem;
            background: rgba(251,252,254,0.96); backdrop-filter: blur(10px);
            border-bottom: 1px solid var(--line); margin: -0.2rem 0 0.8rem; padding: 0.35rem 0;
        }
        .chat-topbar-title { color: var(--ink); font-size: 1rem; font-weight: 850; letter-spacing: 0; }
        .chat-topbar-spacer { height: 0.1rem; }
        .session-strip {
            display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: center; gap: 0.45rem;
            min-height: 2rem; border: 1px solid var(--line); background: var(--surface); border-radius: 0.45rem; padding: 0 0.58rem;
        }
        .session-strip-label { color: var(--muted); font-size: 0.62rem; font-weight: 800; text-transform: uppercase; }
        .session-strip-value { color: #344054; font-size: 0.72rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .inline-status {
            display: flex; align-items: center; gap: 0.48rem; border: 1px solid var(--line);
            border-radius: 0.45rem; padding: 0.52rem 0.62rem; margin: 0.35rem 0; background: var(--surface);
            font-size: 0.84rem; line-height: 1.45;
        }
        .inline-status b { font-size: 0.72rem; text-transform: uppercase; color: var(--muted); min-width: fit-content; }
        .inline-status-success { border-color: #a7f3d0; background: #ecfdf5; color: #065f46; }
        .inline-status-warning { border-color: #fde68a; background: #fffbeb; color: var(--amber); }
        .inline-status-error { border-color: #fecaca; background: #fff1f2; color: var(--red); }
        div[data-testid="stButton"] button, button[data-testid="stBaseButton-secondary"], button[data-testid="stBaseButton-primary"] {
            min-height: 2.05rem !important; border-radius: 0.45rem !important; font-size: 0.76rem !important; font-weight: 750 !important;
        }
        button[data-testid="stBaseButton-primary"] { background: var(--blue) !important; border-color: var(--blue) !important; color: #fff !important; }
        button[data-testid="stBaseButton-primary"]:hover { background: var(--blue-dark) !important; border-color: var(--blue-dark) !important; }
        div[data-testid="stTabs"] button[role="tab"] { font-size: 0.78rem; min-height: 2.1rem; }
        [data-testid="stChatInput"] textarea { min-height: 2.55rem !important; font-size: 0.86rem !important; }
        [data-testid*="ChatMessageAvatar"] { width: 1.95rem !important; height: 1.95rem !important; }
        div[data-testid="stCode"] code, div[data-testid="stCodeBlock"] code {
            font-size: 0.72rem !important; line-height: 1.38 !important;
        }
        .compact-json-block {
            background: #111827; color: #e5e7eb; border-radius: 0.45rem; padding: 0.72rem 0.82rem;
            font-size: 0.68rem !important; line-height: 1.42; white-space: pre-wrap; border: 1px solid #1f2937;
        }
        .compact-json-null { color: #9ca3af; }
        .compact-json-boolean { color: #5eead4; }
        div[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 0.45rem; overflow: hidden; }
        h4 { font-size: 0.98rem !important; }
        @media (max-width: 780px) {
            .chat-topbar { align-items: flex-start; flex-direction: column; }
            .session-strip { width: 100%; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
