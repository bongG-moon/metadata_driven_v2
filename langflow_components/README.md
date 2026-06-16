# Langflow Components

This folder contains standalone custom components for Langflow Desktop.

## Custom Component Shape

Langflow Desktop scans only top-level classes when it builds a custom component.
Each component file must keep this shape:

```python
from lfx.custom.custom_component.component import Component


class MyComponent(Component):
    ...
```

Do not wrap the `Component` import or class definition in `try:`, `if LANGFLOW_AVAILABLE:`,
or another conditional block. The code can be standalone without sibling imports, but the
`Component` subclass itself must be visible at module top level.

## Split Flow Direction

The recommended production shape is now a backend-orchestrated split flow:

1. `router_flow/` classifies the user request and returns `selected_flow`.
2. Backend orchestrator calls one of `metadata_qa_flow/`, `data_analysis_flow/`, `report_generation_flow/`, or `operations_diagnosis_flow/`.
3. `main_flow/` remains as a combined compatibility canvas while existing Langflow deployments are migrated.

This keeps metadata/help/catalog questions out of the heavy data-analysis path and makes future request types additive.

## Component Rules

- Do not import sibling project files from numbered component files.
- Pass compact `payload` dictionaries between nodes.
- Pass compact previous `state.current_data` into request loader nodes when possible.
- In `data_analysis_flow/`, call `05 MongoDB Data Loader` only through the `04 Previous Result Restore Router` branch when full previous rows are required.
- Store source `runtime_sources` and pandas `analysis.rows` in the MongoDB result collection immediately after pandas execution.
- Preserve `state`, `current_data`, `followup_source_results`, and `data_ref` fields for follow-up questions.
- For operating inside Langflow Desktop, prefer the `lfx.*` imports used by the generated files.

## Flow Connection Guides

Detailed wiring guides now live with each flow folder:

- `main_flow/CONNECTION_GUIDE.md`
- `router_flow/CONNECTION_GUIDE.md`
- `metadata_qa_flow/CONNECTION_GUIDE.md`
- `data_analysis_flow/CONNECTION_GUIDE.md`
- `report_generation_flow/CONNECTION_GUIDE.md`
- `operations_diagnosis_flow/CONNECTION_GUIDE.md`
- `domain_authoring_flow/CONNECTION_GUIDE.md`
- `table_catalog_authoring_flow/CONNECTION_GUIDE.md`
- `main_flow_filters_authoring_flow/CONNECTION_GUIDE.md`

## Combined Main Flow LLM Node Pattern

The sequence below applies to the compatibility `main_flow/` canvas. For new runtime wiring, start with `router_flow/` and then call the selected subflow.

Use Langflow's Gemini/LLM nodes for the actual reasoning calls:

1. `03 Route Candidate Builder.payload_out -> 04 Route Classifier Prompt Builder`; call a small Gemini/LLM route classifier only when `route_llm_required=true`.
2. `03 Route Candidate Builder.payload_out` plus optional route LLM text -> `05 Route Classifier Normalizer -> 06 Metadata QA Response Builder`.
3. `07 Intent Prompt Builder.intent_prompt -> Gemini/LLM -> 08 Intent Plan Normalizer.llm_response`
4. `09~14` main_flow retriever nodes -> `15 Retrieval Payload Adapter.payload`
5. `15 Retrieval Payload Adapter.payload -> 16 Pandas Prompt Builder` and `17 Pandas Code Executor`
6. `16 Pandas Prompt Builder.pandas_prompt -> Gemini/LLM -> 17 Pandas Code Executor.llm_response`
7. `17 Pandas Code Executor.payload_out -> 18 MongoDB Data Store.payload`
8. `18 MongoDB Data Store.payload_out -> 19 Answer Prompt Builder.payload` and `20 Answer Response Builder.payload`
9. `19 Answer Prompt Builder.answer_prompt -> Gemini/LLM -> 20 Answer Response Builder.llm_response`
10. `20 Answer Response Builder.payload_out -> 21 Answer Message Adapter.message -> Chat Output`

The final adapter formats one playground-friendly Markdown message from the existing final payload.
It includes the answer, result table, intent summary, retrieval/step plan summary, pandas execution
status, and generated pandas code without adding another payload branch.

The deterministic files under `demo_flow/` are fallback examples for local checks. They are not the
recommended production Langflow path.

## Metadata Authoring Flow Pattern

The three metadata authoring flows use the same shape:

1. request loader with existing MongoDB metadata summary
2. text refinement prompt -> Gemini/LLM -> refinement normalizer
3. authoring prompt -> Gemini/LLM -> authoring result normalizer
4. similarity checker for same or confusingly similar existing metadata
5. review prompt -> Gemini/LLM -> review writer
6. response builder for Playground/API output

The review writer saves only when the review says the item is ready and no duplicate choice is pending.


