"""Canonical identities for the four prompt paths used by formal runs."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _string_literals(
    path: Path,
    *,
    function_name: str,
    class_name: str = "",
    assignments: Iterable[str] = (),
) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    selected: list[ast.AST] = []
    assignment_names = set(assignments)
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id in assignment_names for target in targets):
                selected.append(node)
        if class_name and isinstance(node, ast.ClassDef) and node.name == class_name:
            selected.extend(
                child
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and child.name == function_name
            )
        elif not class_name and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                selected.append(node)
    if not selected:
        raise ValueError(f"Prompt source not found: {path}:{class_name}.{function_name}")
    return [
        node.value
        for selected_node in selected
        for node in ast.walk(selected_node)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.strip()
    ]


def build_prompt_identity_manifest(*, source_commit: str) -> dict[str, Any]:
    task_prompt = ROOT / "agent/prompts/task_prompt.txt"
    prompt_template = ROOT / "agent/prompts/prompt_template.txt"
    work_memory = ROOT / "agent/work_memory.py"
    reflexion = ROOT / "agent/reflexion.py"
    confidence = ROOT / "dc3pa/reliability/ordinal_confidence.py"
    evaluation = ROOT / "dc3pa/evaluation/chain.py"

    payloads: Mapping[str, Any] = {
        "planner": {
            "task_prompt": task_prompt.read_text(encoding="utf-8"),
            "prompt_template": prompt_template.read_text(encoding="utf-8"),
            "dynamic_literals": _string_literals(
                work_memory,
                class_name="Work_Memory",
                function_name="generate_prompt_template",
            ),
        },
        "confidence": {
            "literals": _string_literals(
                confidence,
                function_name="build_ordinal_confidence_prompt",
                assignments=("_ORDINAL_INSTRUCTION",),
            )
        },
        "evaluation": {
            "literals": _string_literals(
                evaluation,
                function_name="build_evaluation_prompt",
            )
        },
        "reflexion": {
            "literals": _string_literals(
                reflexion,
                class_name="Reflexion",
                function_name="reflect_failure",
            )
        },
    }
    prompt_hashes = {name: _sha(payload) for name, payload in payloads.items()}
    source_files = {
        str(path.relative_to(ROOT)): _file_sha(path)
        for path in (
            task_prompt,
            prompt_template,
            work_memory,
            reflexion,
            confidence,
            evaluation,
        )
    }
    body = {
        "schema_version": 1,
        "source_commit": source_commit,
        "prompt_hashes": prompt_hashes,
        "source_file_sha256": source_files,
        "canonicalization": "UTF-8 content and ordered AST string literals; canonical JSON",
    }
    body["manifest_id"] = _sha(body)
    return body


__all__ = ["build_prompt_identity_manifest"]
