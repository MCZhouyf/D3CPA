#!/usr/bin/env python3
"""Find task/item-conditioned control-flow in Python source files."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


TASK_KEYS = {"task", "task_id", "task_name", "difficulty", "tier"}
TARGET_LITERALS = {"diamond", "redstone", "gold", "deep mining"}


def _literal_strings(node: ast.AST) -> set[str]:
    return {
        child.value.strip().lower()
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    }


def _uses_task_value(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Subscript) and isinstance(child.slice, ast.Constant):
            if str(child.slice.value) in TASK_KEYS:
                return True
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            if child.func.attr == "get" and child.args:
                first = child.args[0]
                if isinstance(first, ast.Constant) and str(first.value) in TASK_KEYS:
                    return True
    return False


def scan(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    excluded = {".git", "__pycache__", ".pytest_cache", "logs", "runs", "artifacts"}
    for path in sorted(root.rglob("*.py")):
        if any(part in excluded for part in path.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            findings.append({"file": str(path.relative_to(root)), "parse_error": str(exc)})
            continue
        for node in ast.walk(tree):
            condition = node.test if isinstance(node, (ast.If, ast.IfExp, ast.While)) else None
            if condition is None:
                continue
            literals = _literal_strings(condition)
            if _uses_task_value(condition) or literals & TARGET_LITERALS:
                findings.append(
                    {
                        "file": str(path.relative_to(root)),
                        "line": int(node.lineno),
                        "kind": type(node).__name__,
                        "task_conditioned": _uses_task_value(condition),
                        "target_literals": sorted(literals & TARGET_LITERALS),
                        "condition": ast.unparse(condition),
                    }
                )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    findings = scan(args.root.resolve())
    payload = {"findings": findings, "count": len(findings)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"count": len(findings)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
