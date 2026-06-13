# Langflow Implementation Guide

이 문서는 metadata-driven manufacturing agent를 Langflow 기반으로 구현할 때 지켜야 할 구현 방향을 정리한다.

## Goal

이 agent는 특정 제조 조직에만 묶이지 않아야 한다. 같은 Langflow flow 구조에서 `domain`, `table_catalog`, `main_flow_filters` metadata만 바꾸면 각 조직이 사용하는 업무 용어와 데이터 기준으로 조회와 분석이 가능해야 한다.

구현의 중심은 다음이다.

- 사용자의 실제 업무 용어를 metadata와 연결한다.
- 질문을 사람이 사고하듯 순서가 있는 실행 단계로 나눈다.
- 데이터 조회는 별도 retrieval flow가 담당한다.
- dummy data도 main flow shortcut이 아니라 별도 `01 Dummy Data Retriever`를 통해 조회한다.
- 통합 분석과 계산은 pandas code로 수행한다.
- Gemini/LLM node는 Langflow 기본 LLM node를 사용한다.
- custom component는 standalone으로 작성하고, sibling helper import에 의존하지 않는다.

## Main Flow Order

실제 Langflow canvas에 붙일 권장 component 순서는 아래와 같다.

1. `00_request_state_loader.py`
2. `01_metadata_context_loader.py`
3. `02_intent_prompt_builder.py`
4. Gemini/LLM intent JSON node
5. `03_intent_plan_normalizer.py`
6. data retrieval flow
7. `04_retrieval_payload_adapter.py`
8. `05_pandas_prompt_builder.py`
9. Gemini/LLM pandas code JSON node
10. `06_pandas_code_executor.py`
11. `07_answer_prompt_builder.py`
12. Gemini/LLM final answer node
13. `08_answer_response_builder.py`
14. `09_answer_message_adapter.py`

LLM 없이 동작하는 deterministic 예시는 `langflow_components/demo_flow/`에 따로 둔다. 운영 권장 canvas는 `langflow_components/main_flow/`와 `langflow_components/data_retrieval_flow/`의 조합을 따른다.

## Retrieval Flow Choices

retrieval은 두 방식 중 하나를 쓴다.

### Dummy

```text
03 Intent Plan Normalizer.payload_out -> 01 Dummy Data Retriever.payload
03 Intent Plan Normalizer.payload_out -> 04 Retrieval Payload Adapter.main_payload
01 Dummy Data Retriever.retrieval_payload -> 04 Retrieval Payload Adapter.retrieval_payload
04 Retrieval Payload Adapter.payload -> 05 Pandas Prompt Builder.payload
04 Retrieval Payload Adapter.payload -> 06 Pandas Code Executor.payload
```

### Four Sources

```text
03 Intent Plan Normalizer.payload_out -> 02 Oracle Query Retriever.payload
03 Intent Plan Normalizer.payload_out -> 03 H-API Retriever.payload
03 Intent Plan Normalizer.payload_out -> 04 Datalake Retriever.payload
03 Intent Plan Normalizer.payload_out -> 05 Goodocs Retriever.payload
03 Intent Plan Normalizer.payload_out -> 04 Retrieval Payload Adapter.main_payload

02 Oracle Query Retriever.retrieval_payload -> 06 Source Retrieval Merger.oracle_retrieval
03 H-API Retriever.retrieval_payload -> 06 Source Retrieval Merger.h_api_retrieval
04 Datalake Retriever.retrieval_payload -> 06 Source Retrieval Merger.datalake_retrieval
05 Goodocs Retriever.retrieval_payload -> 06 Source Retrieval Merger.goodocs_retrieval

06 Source Retrieval Merger.retrieval_payload -> 04 Retrieval Payload Adapter.retrieval_payload
04 Retrieval Payload Adapter.payload -> 05 Pandas Prompt Builder.payload
04 Retrieval Payload Adapter.payload -> 06 Pandas Code Executor.payload
```

## LLM Placement

Langflow의 Gemini/LLM node는 세 위치에 둔다.

- Intent planning: `02 Intent Prompt Builder -> Gemini/LLM -> 03 Intent Plan Normalizer`
- Pandas code generation: `05 Pandas Prompt Builder -> Gemini/LLM -> 06 Pandas Code Executor`
- Final answer writing: `07 Answer Prompt Builder -> Gemini/LLM -> 08 Answer Response Builder`

LLM 출력은 그대로 신뢰하지 않는다. intent JSON은 normalizer에서 dataset key, source alias, params, filter scope를 metadata와 대조하고, pandas code JSON은 safety check를 통과한 뒤 in-memory DataFrame에만 실행한다.

## Payload Contract

중간 payload는 compact하게 유지한다.

- `request`: session id, question, timezone
- `state`: `chat_history`, `context`, `current_data`
- `metadata`: domain, table catalog, main flow filters
- `intent_plan`: normalized intent, analysis kind, step plan
- `retrieval_jobs`: dataset별 조회 요청
- `runtime_sources`: pandas 실행 전까지 유지하는 source rows
- `source_results`: compact retrieval trace
- `analysis`: pandas 실행 결과
- `data`: 최종 사용자 표시 데이터
- `applied_scope`: 적용 dataset, filter, params, metadata refs
- `answer_message`: 최종 답변

최종 payload에서는 `runtime_sources`를 제거하고 `data.rows`와 source trace만 유지한다. 운영에서는 `data_ref`를 MongoDB/cache 저장소 key로 연결하는 구조를 권장한다.

Langflow Playground에서 매번 각 노드의 result를 열어보지 않아도 되도록, `09_answer_message_adapter.py`는 최종 payload를 Chat Output용 Markdown으로 표시한다. 표시 내용은 payload를 새로 중복 저장하지 않고 기존 `answer_message`, `data`, `intent_plan`, `applied_scope`, `analysis`를 읽어서 만든다.

- 답변 내용
- 결과 테이블과 row count
- intent route, analysis kind, step plan, retrieval job
- pandas 실행 상태, reasoning step, LLM 생성 pandas code

## Standalone Component Rules

- 각 numbered custom component는 하나의 파일만 Langflow에 붙여도 동작해야 한다.
- `from reference_runtime import ...`, `from .utils import ...`, `from langflow_components... import ...` 같은 sibling/project import를 사용하지 않는다.
- 파일 최상위에 `class Something(Component)`가 있어야 한다.
- input 이름과 output 이름을 같은 component 안에서 겹치게 만들지 않는다.
- process-specific rule은 Python code보다 domain/table catalog/main flow filter metadata 또는 prompt contract에 둔다.

## Validation

기본 검증:

```powershell
cd C:\Users\qkekt\Desktop\metadata_driven_v2
python -m pytest tests -q
python -m compileall -q reference_runtime langflow_components tools tests
```

Langflow Desktop component parser 검증:

```powershell
$py='C:\Users\qkekt\AppData\Local\com.LangflowDesktop\.langflow-venv\Scripts\python.exe'
$script=@'
from pathlib import Path
from lfx.custom.eval import eval_custom_component_code
root = Path(r'C:\Users\qkekt\Desktop\metadata_driven_v2\langflow_components')
for path in sorted(root.rglob('*.py')):
    code = path.read_text(encoding='utf-8')
    cls = eval_custom_component_code(code)
    instance = cls(_code=code)
print('init_ok')
'@
$script | & $py -
```

대표 smoke 질문은 `docs/LANGFLOW_NODE_CONNECTION_GUIDE.md`를 따른다.
