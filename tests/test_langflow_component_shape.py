from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_langflow_components_define_top_level_component_subclass() -> None:
    component_files = sorted((PROJECT_ROOT / "langflow_components").rglob("*.py"))
    assert component_files

    for path in component_files:
        code = path.read_text(encoding="utf-8")
        module = ast.parse(code)
        class_names = []
        for node in module.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                if isinstance(base, ast.Name) and "Component" in base.id:
                    class_names.append(node.name)

        assert class_names, f"{path} must define a top-level Component subclass"
        assert "LANGFLOW_AVAILABLE" not in code, f"{path} must not hide the class behind an availability guard"


def test_langflow_components_do_not_reuse_input_names_as_output_names() -> None:
    component_files = sorted((PROJECT_ROOT / "langflow_components").rglob("*.py"))

    for path in component_files:
        module_name = f"component_shape_{path.stem}".replace(".", "_")
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        component_classes = []
        for value in module.__dict__.values():
            if isinstance(value, type):
                for base in value.__bases__:
                    if base.__name__ == "_Component" or "Component" in base.__name__:
                        component_classes.append(value)

        assert component_classes, f"{path} must define a Component subclass"
        for component_class in component_classes:
            input_names = {getattr(item, "name", None) for item in getattr(component_class, "inputs", [])}
            output_names = {getattr(item, "name", None) for item in getattr(component_class, "outputs", [])}
            input_names.discard(None)
            output_names.discard(None)
            overlap = input_names.intersection(output_names)
            assert not overlap, f"{path} has overlapping input/output names: {sorted(overlap)}"


def test_main_flow_files_use_clean_sequential_numbering() -> None:
    expected_files = [
        "00_request_state_loader.py",
        "01_metadata_context_loader.py",
        "02_intent_prompt_builder.py",
        "03_intent_plan_normalizer.py",
        "04_retrieval_payload_adapter.py",
        "05_pandas_prompt_builder.py",
        "06_pandas_code_executor.py",
        "07_answer_prompt_builder.py",
        "08_answer_response_builder.py",
        "09_answer_message_adapter.py",
    ]
    actual_files = [path.name for path in sorted((PROJECT_ROOT / "langflow_components" / "main_flow").glob("*.py"))]
    assert actual_files == expected_files

    for index, path in enumerate(sorted((PROJECT_ROOT / "langflow_components" / "main_flow").glob("*.py"))):
        module_name = f"main_flow_order_{path.stem}".replace(".", "_")
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        display_names = [
            getattr(value, "display_name", "")
            for value in module.__dict__.values()
            if isinstance(value, type) and any("Component" in base.__name__ for base in value.__bases__)
        ]
        assert display_names, f"{path} must define a display_name"
        assert display_names[0].startswith(f"{index:02d} "), f"{path.name} display_name should start with {index:02d}"
