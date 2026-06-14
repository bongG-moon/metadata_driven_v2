# Langflow Node Connection Guide Index

상세 node 연결표는 각 flow 폴더 안으로 옮겼습니다. Langflow canvas를 처음 만들 때는 전체 wiring을 한 번에 정리한 `docs/V2_LANGFLOW_CANVAS_WIRING_GUIDE.md`를 먼저 보고, 세부 component별 보조 정보가 필요할 때 각 flow 폴더의 `CONNECTION_GUIDE.md`를 기준으로 연결하면 됩니다.

| Flow | Detailed guide |
| --- | --- |
| V2 전체 canvas wiring | `docs/V2_LANGFLOW_CANVAS_WIRING_GUIDE.md` |
| Main query/analysis flow | `langflow_components/main_flow/CONNECTION_GUIDE.md` |
| Data retrieval flow | `langflow_components/data_retrieval_flow/CONNECTION_GUIDE.md` |
| Domain metadata authoring flow | `langflow_components/domain_authoring_flow/CONNECTION_GUIDE.md` |
| Table catalog authoring flow | `langflow_components/table_catalog_authoring_flow/CONNECTION_GUIDE.md` |
| Main flow filter authoring flow | `langflow_components/main_flow_filters_authoring_flow/CONNECTION_GUIDE.md` |
| Web implementation guide | `docs/WEB_IMPLEMENTATION_GUIDE.md` |

공통 원칙은 유지합니다.

- 실제 reasoning과 JSON 생성은 Langflow의 Gemini/LLM 노드가 담당합니다.
- custom component는 prompt 생성, LLM 응답 정규화, payload 병합, 검증, 저장, 응답 정리를 담당합니다.
- numbered custom component는 standalone이어야 하며 sibling helper module을 import하지 않습니다.
- 같은 component 안에서 input 이름과 output 이름이 겹치지 않게 합니다.
- payload에는 다음 단계에 필요한 compact 정보만 남기고 prompt 전문이나 중복 row를 계속 복사하지 않습니다.
