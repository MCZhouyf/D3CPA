#!/usr/bin/env python3
"""Statically inventory direct state writes relevant to formal episodes."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


def _target_text(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover
        return type(node).__name__


def scan(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    excluded = {".git", "__pycache__", ".pytest_cache", "logs", "runs", "artifacts"}
    for path in sorted(root.rglob("*.py")):
        if any(part in excluded for part in path.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        rel = str(path.relative_to(root))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"set_inventory", "set_state", "inject"}:
                    findings.append({
                        "file": rel, "line": int(node.lineno), "kind": "call",
                        "callee": _target_text(node.func), "expression": _target_text(node),
                    })
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    text = _target_text(target)
                    if ".inventory" in text or text.endswith("inventory"):
                        findings.append({
                            "file": rel, "line": int(node.lineno), "kind": type(node).__name__,
                            "target": text, "expression": _target_text(node),
                        })
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
