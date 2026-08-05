#!/usr/bin/env python3
"""Verify that the protected log-callback region matches ``success-finish``.

This verifier intentionally compares normalized Python ASTs, not file hashes, so
unrelated controller changes are permitted while semantic changes to the callback
region are rejected.  The protected symbols are the existing delayed callback,
its inventory write, and its direct Controller helpers.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_CONTROLLER = Path("MP5_agent/agent/controller.py")
PROTECTED_SYMBOLS = (
    "_sync_memory",
    "_set_inventory_from_memory",
    "_begin_log_callback_window",
    "_log_callback_due",
    "_complete_log_callback_window",
    "_gather_logs",
)
PROTECTED_CONSTANTS = ("_LOG_CALLBACK_DELAY_STEPS",)
CALL_SITES = (
    ("_gather_logs", "_set_inventory_from_memory"),
    ("_gather_logs", "_begin_log_callback_window"),
    ("_gather_logs", "_log_callback_due"),
    ("_gather_logs", "_complete_log_callback_window"),
)


def _normalized(node: ast.AST) -> str:
    return ast.dump(node, annotate_fields=True, include_attributes=False)


def _digest(node: ast.AST) -> str:
    return hashlib.sha256(_normalized(node).encode("utf-8")).hexdigest()


def _parse(source: str, label: str) -> ast.Module:
    try:
        return ast.parse(source, filename=label)
    except SyntaxError as exc:  # pragma: no cover - an explicit verifier failure
        raise RuntimeError(f"cannot parse {label}: {exc}") from exc


def _controller_body(tree: ast.Module) -> list[ast.stmt]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Controller":
            return node.body
    raise RuntimeError("Controller class not found")


def _symbol_nodes(source: str, label: str) -> dict[str, ast.AST]:
    body = _controller_body(_parse(source, label))
    result: dict[str, ast.AST] = {}
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in PROTECTED_SYMBOLS:
            result[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in PROTECTED_CONSTANTS:
                    result[target.id] = node
    missing = (set(PROTECTED_SYMBOLS) | set(PROTECTED_CONSTANTS)) - set(result)
    if missing:
        raise RuntimeError(f"protected callback symbols missing: {sorted(missing)}")
    return result


def _call_nodes(symbols: dict[str, ast.AST]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for caller, callee in CALL_SITES:
        matches: list[ast.Call] = []
        for node in ast.walk(symbols[caller]):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == callee:
                matches.append(node)
        if not matches:
            raise RuntimeError(
                f"expected a protected call {caller}->{callee}, found none"
            )
        for ordinal, call in enumerate(matches):
            entries.append(
                {
                    "caller": caller,
                    "callee": callee,
                    "ordinal": ordinal,
                    "line": int(getattr(call, "lineno", -1)),
                    "normalized_ast_sha256": _digest(call),
                }
            )
    return entries


def _git_show(repo: Path, revision: str, path: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), "show", f"{revision}:{path.as_posix()}"],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def manifest(
    repo: Path,
    baseline: str,
    current_path: Path,
    runtime_trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    baseline_source = _git_show(repo, baseline, current_path)
    current_source = (repo / current_path).read_text(encoding="utf-8")
    baseline_symbols = _symbol_nodes(baseline_source, f"{baseline}:{current_path}")
    current_symbols = _symbol_nodes(current_source, str(current_path))
    baseline_commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", f"{baseline}^{{}}"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    definitions = []
    for name in (*PROTECTED_CONSTANTS, *PROTECTED_SYMBOLS):
        node = baseline_symbols[name]
        definitions.append(
            {
                "file": current_path.as_posix(),
                "symbol": name,
                "start_line": int(getattr(node, "lineno", -1)),
                "end_line": int(getattr(node, "end_lineno", -1)),
                "normalized_ast_sha256": _digest(node),
            }
        )
    callback_call_sites = _call_nodes(baseline_symbols)
    for item in callback_call_sites:
        item["file"] = current_path.as_posix()
    return {
        "baseline_tag": baseline,
        "baseline_commit": baseline_commit,
        "definitions": definitions,
        "call_sites": callback_call_sites,
        "direct_helpers": ["Controller._sync_memory"],
        "config_keys": ["Controller._LOG_CALLBACK_DELAY_STEPS"],
        "inventory_write_sites": [
            {
                "file": current_path.as_posix(),
                "symbol": "Controller._set_inventory_from_memory",
                "call": "env.set_inventory",
            }
        ],
        "runtime_trace": list(runtime_trace or []),
        "notes": [
            "Protected boundary includes the existing delayed log callback and its direct Controller helper.",
            "Calls into _gather_logs outside the callback implementation are audited separately because they may be prohibited automatic recovery paths.",
        ],
        "current_definitions": {
            name: _digest(node) for name, node in current_symbols.items()
        },
        "baseline_definitions": {
            name: _digest(node) for name, node in baseline_symbols.items()
        },
        "current_call_sites": [
            {"file": current_path.as_posix(), **item}
            for item in _call_nodes(current_symbols)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", default="success-finish")
    parser.add_argument("--controller", type=Path, default=DEFAULT_CONTROLLER)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--runtime-trace", type=Path)
    args = parser.parse_args()
    trace: list[dict[str, Any]] | None = None
    if args.runtime_trace:
        trace_payload = json.loads(args.runtime_trace.read_text(encoding="utf-8"))
        trace = trace_payload if isinstance(trace_payload, list) else [dict(trace_payload)]
    data = manifest(args.repo.resolve(), args.baseline, args.controller, trace)
    def call_identity(entry: dict[str, Any]) -> tuple[Any, ...]:
        # Line numbers are retained for audit readability but are not a semantic
        # location: unrelated imports may shift them without changing either the
        # callback function or its contained call expression.
        return (
            entry["file"], entry["caller"], entry["callee"], entry["ordinal"],
            entry["normalized_ast_sha256"],
        )

    unchanged = (
        data["baseline_definitions"] == data["current_definitions"]
        and [call_identity(item) for item in data["call_sites"]]
        == [call_identity(item) for item in data["current_call_sites"]]
    )
    data["unchanged"] = unchanged
    if args.manifest:
        target = args.repo / args.manifest
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"unchanged": unchanged, "baseline": data["baseline_commit"]}, sort_keys=True))
    return 0 if unchanged else 1


if __name__ == "__main__":
    raise SystemExit(main())
