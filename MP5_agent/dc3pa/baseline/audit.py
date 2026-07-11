from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable, List, Sequence


@dataclass(frozen=True)
class AuditFinding:
    path: str
    line: int
    severity: str
    category: str
    evidence: str
    rationale: str

    def to_dict(self):
        return asdict(self)


_RULES = (
    (
        "critical",
        "environment_state_mutation",
        re.compile(r"\bset_inventory\s*\("),
        "Direct inventory mutation can bypass environment dynamics and confound results.",
    ),
    (
        "high",
        "task_specific_branch",
        re.compile(r"\b(diamond|redstone)\b", re.IGNORECASE),
        "Task-name-specific logic must be isolated from research-mode comparisons.",
    ),
    (
        "high",
        "fixed_workflow",
        re.compile(r"fixed_workflow|_fixed_workflow_for_task"),
        "A hand-authored workflow can dominate planner performance.",
    ),
    (
        "high",
        "prerequisite_injection",
        re.compile(r"inject_prerequisite|prerequisite_steps"),
        "Planner-side prerequisite injection overlaps the proposed knowledge evaluator.",
    ),
    (
        "medium",
        "fallback_behavior",
        re.compile(r"\bfallback\b|_fallback_", re.IGNORECASE),
        "Fallbacks should be logged and separated from high-level planning gains.",
    ),
    (
        "medium",
        "hardcoded_seed",
        re.compile(r"\b(?:world_seed|seed)\s*=\s*\d+\b"),
        "Hard-coded simulator seeds should be explicit run parameters.",
    ),
    (
        "medium",
        "uncontrolled_randomness",
        re.compile(
            r"random\.(?:randint|random|choice|uniform|randrange|shuffle|sample)\b"
            r"|np\.random\.(?!seed\b)[A-Za-z_]\w*"
        ),
        "Uncontrolled randomness weakens reproducibility.",
    ),
)

DEFAULT_FILES = (
    "MP5_agent/agent/planner.py",
    "MP5_agent/agent/run_agent.py",
    "MP5_agent/agent/controller.py",
    "MP5_agent/agent/work_memory.py",
)


def audit_paths(paths: Iterable[str | Path]) -> List[AuditFinding]:
    findings: List[AuditFinding] = []
    for path_like in paths:
        path = Path(path_like)
        if not path.exists() or not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, start=1):
            for severity, category, pattern, rationale in _RULES:
                if pattern.search(line):
                    findings.append(
                        AuditFinding(
                            path=str(path),
                            line=line_number,
                            severity=severity,
                            category=category,
                            evidence=line.strip()[:300],
                            rationale=rationale,
                        )
                    )
    return findings


def audit_legacy_sources(repo_root: str | Path) -> List[AuditFinding]:
    root = Path(repo_root).resolve()
    findings = audit_paths(root / relative for relative in DEFAULT_FILES)
    portable: List[AuditFinding] = []
    for finding in findings:
        path = Path(finding.path)
        try:
            display_path = str(path.resolve().relative_to(root))
        except ValueError:
            display_path = path.name
        portable.append(replace(finding, path=display_path))
    return portable


def write_audit_report(findings: Sequence[AuditFinding], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    counts = {}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    report = {
        "summary": {"count": len(findings), "by_severity": counts},
        "findings": [finding.to_dict() for finding in findings],
    }
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
