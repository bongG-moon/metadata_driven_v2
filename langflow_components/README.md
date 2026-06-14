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

## Component Rules

- Do not import sibling project files from numbered component files.
- Pass compact `payload` dictionaries between nodes.
- Load previous-turn `data_ref` pointers with `01 MongoDB Data Loader` in preview mode before follow-up planning; place a second `01 MongoDB Data Loader` after node 04 with `hydrate_mode=auto` so full rows are loaded only when the normalized intent requires them.
- Store source `runtime_sources` and pandas `analysis.rows` in the MongoDB result collection with `08 MongoDB Data Store` immediately after pandas execution.
- Preserve `state`, `current_data`, `followup_source_results`, and `data_ref` fields for follow-up questions.
- For operating inside Langflow Desktop, prefer the `lfx.*` imports used by the generated files.

## Flow Connection Guides

Detailed wiring guides now live with each flow folder:

- `main_flow/CONNECTION_GUIDE.md`
- `data_retrieval_flow/CONNECTION_GUIDE.md`
- `domain_authoring_flow/CONNECTION_GUIDE.md`
- `table_catalog_authoring_flow/CONNECTION_GUIDE.md`
- `main_flow_filters_authoring_flow/CONNECTION_GUIDE.md`

## Recommended LLM Node Pattern

Use Langflow's Gemini/LLM nodes for the actual reasoning calls:

1. `03 Intent Prompt Builder.intent_prompt -> Gemini/LLM -> 04 Intent Plan Normalizer.llm_response`
2. data retrieval flow -> `05 Retrieval Payload Adapter.payload`
3. `05 Retrieval Payload Adapter.payload -> 06 Pandas Prompt Builder` and `07 Pandas Code Executor`
4. `06 Pandas Prompt Builder.pandas_prompt -> Gemini/LLM -> 07 Pandas Code Executor.llm_response`
5. `07 Pandas Code Executor.payload_out -> 08 MongoDB Data Store.payload`
6. `08 MongoDB Data Store.payload_out -> 09 Answer Prompt Builder.payload` and `10 Answer Response Builder.payload`
7. `09 Answer Prompt Builder.answer_prompt -> Gemini/LLM -> 10 Answer Response Builder.llm_response`
8. `10 Answer Response Builder.payload_out -> 11 Answer Message Adapter.message -> Chat Output`

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
