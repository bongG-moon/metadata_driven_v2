# Router Flow Connection Guide

`router_flow`는 사용자의 질문을 먼저 받아서 실제 실행할 하위 flow를 선택하는 앞단 분기 flow입니다. 이 flow는 데이터 조회, pandas 실행, 결과 저장을 하지 않습니다.

## Output Contract

마지막 `05 Orchestrator Response Builder.route_response`를 backend orchestrator가 읽습니다.

```json
{
  "response_type": "route_decision",
  "route": "metadata_qa | data_analysis | report_generation | operations_diagnosis | direct_answer",
  "selected_flow": "metadata_qa_flow | data_analysis_flow | report_generation_flow | operations_diagnosis_flow",
  "flow_id_env": "LANGFLOW_..._FLOW_ID",
  "flow_inputs": {
    "question": "...",
    "session_id": "...",
    "state": {},
    "metadata_route": {},
    "metadata": {}
  }
}
```

## Sequence

```text
Chat Input
-> 00 Router Request Loader
-> 01 Metadata Context Loader
-> 02 Route Candidate Builder
-> 03 Route Classifier Prompt Builder
-> Route Classifier LLM
-> 04 Route Classifier Normalizer
-> 05 Orchestrator Response Builder
-> Backend orchestrator
```

`02`가 `route_llm_required=false`를 만든 확실한 greeting/help 케이스는 backend에서 Route Classifier LLM 호출을 생략할 수 있습니다. 애매한 질문은 작은 route classifier LLM을 통과시켜 `metadata_qa`, `data_analysis`, `report_generation`, `operations_diagnosis` 중 하나로 분류합니다.

## Backend Routing

| route | selected_flow | Env |
| --- | --- | --- |
| `direct_answer` | `metadata_qa_flow` | `LANGFLOW_METADATA_QA_FLOW_ID` |
| `metadata_qa` | `metadata_qa_flow` | `LANGFLOW_METADATA_QA_FLOW_ID` |
| `data_analysis` | `data_analysis_flow` | `LANGFLOW_DATA_ANALYSIS_FLOW_ID` |
| `report_generation` | `report_generation_flow` | `LANGFLOW_REPORT_GENERATION_FLOW_ID` |
| `operations_diagnosis` | `operations_diagnosis_flow` | `LANGFLOW_OPERATIONS_DIAGNOSIS_FLOW_ID` |
