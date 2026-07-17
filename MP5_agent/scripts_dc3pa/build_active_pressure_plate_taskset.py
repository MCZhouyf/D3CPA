#!/usr/bin/env python3
"""Build the superseding active pressure-plate task tree outside Git."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.taskset_canonicalization import (  # noqa: E402
    NEW_TASK,
    ActiveArtifactDescriptor,
    load_catalog,
)


def _run(command: list[str], *, cwd: Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def build_descriptors(root: Path) -> tuple[ActiveArtifactDescriptor, ...]:
    descriptors = [
        ActiveArtifactDescriptor("final catalog", "final_task_catalog.csv", "catalog", True),
        ActiveArtifactDescriptor(
            "final exclusion", "final_test_exclusion.json", "final_test_exclusion", True
        ),
        ActiveArtifactDescriptor(
            "reference v1",
            "reconstructed_v1/reconstructed_v1_design.json",
            "reference_design_v1",
            True,
        ),
        ActiveArtifactDescriptor(
            "reference v2", "schema_v2/reference_design.json", "reference_design_v2", True
        ),
        ActiveArtifactDescriptor(
            "semantic migration",
            "semantic_migration_report.json",
            "semantic_migration",
            False,
        ),
        ActiveArtifactDescriptor("blueprint", "blueprint.json", "blueprint", True),
        ActiveArtifactDescriptor(
            "development protocol", "development_protocol.json", "development_protocol", True
        ),
        ActiveArtifactDescriptor(
            "acquisition schedule",
            "formal_acquisition_schedule.json",
            "acquisition_schedule",
            True,
        ),
        ActiveArtifactDescriptor(
            "acquisition audit",
            "formal_acquisition_audit.json",
            "acquisition_audit",
            True,
        ),
        ActiveArtifactDescriptor(
            "active results report", "ROUND510_ACTIVE_RESULTS.md", "documentation", True
        ),
    ]
    for folder, kind in (
        ("creative_task_jsons", "runtime_task_json"),
        ("formal_task_specs", "formal_task_spec"),
    ):
        for path in sorted((root / folder).glob("*.json")):
            relative = path.relative_to(root).as_posix()
            descriptors.append(
                ActiveArtifactDescriptor(
                    f"{kind}: {path.stem}",
                    relative,
                    kind,
                    kind == "formal_task_spec"
                    and path.name == "craft_wooden_pressure_plate.json",
                )
            )
    return tuple(descriptors)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--canonical-catalog", required=True)
    parser.add_argument("--executed-campaign-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()

    repo = Path(args.repo_root).resolve()
    catalog = Path(args.canonical_catalog).resolve()
    campaign = Path(args.executed_campaign_root).resolve()
    output = Path(args.output_root).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output root is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    load_catalog(catalog)

    _copy_file(catalog, output / "final_task_catalog.csv")
    for folder in ("creative_task_jsons", "formal_task_specs"):
        source = campaign / "approved_tasks" / folder
        if not source.is_dir():
            raise FileNotFoundError(source)
        shutil.copytree(source, output / folder)

    schema_v2 = output / "schema_v2"
    _run(
        [
            sys.executable,
            str(ROOT / "scripts_dc3pa/generate_gpt51_reference_design.py"),
            "--task-catalog",
            str(catalog),
            "--source-commit",
            args.source_commit,
            "--output-dir",
            str(schema_v2),
        ]
    )
    reconstructed_v1 = output / "reconstructed_v1"
    _run(
        [
            sys.executable,
            str(ROOT / "scripts_dc3pa/reconstruct_schema_v1_reference_design.py"),
            "--repo-root",
            str(repo),
            "--task-catalog",
            str(catalog),
            "--output-dir",
            str(reconstructed_v1),
        ]
    )
    _run(
        [
            sys.executable,
            str(ROOT / "scripts_dc3pa/compare_round58_design_semantics.py"),
            "--old-design",
            str(reconstructed_v1 / "reconstructed_v1_design.json"),
            "--new-design",
            str(schema_v2 / "reference_design.json"),
            "--output-report",
            str(output / "semantic_migration_report.json"),
        ]
    )

    _copy_file(schema_v2 / "final_test_exclusion.json", output / "final_test_exclusion.json")
    for source_name, destination_name in (
        ("formal_bootstrap_blueprint.json", "blueprint.json"),
        ("formal_acquisition_schedule.json", "formal_acquisition_schedule.json"),
        ("formal_acquisition_audit.json", "formal_acquisition_audit.json"),
    ):
        _copy_file(campaign / source_name, output / destination_name)

    reference = _load(schema_v2 / "reference_design.json")
    development_protocol = {
        "schema_version": 1,
        "source_commit": args.source_commit,
        "reference_design_id": reference["design_id"],
        "canonical_task": NEW_TASK,
        "development_assignments": reference["development_assignments"],
    }
    (output / "development_protocol.json").write_text(
        json.dumps(development_protocol, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    audit = _load(campaign / "formal_acquisition_audit.json")
    results = "\n".join(
        (
            "# Round 5.10 active pressure-plate results",
            "",
            f"- Canonical active task: `{NEW_TASK}`",
            f"- Acquisition audit ID: `{audit['audit_id']}`",
            f"- Acquisition root SHA-256: `{audit['acquisition_root_sha256']}`",
            f"- Successful episodes: `{audit['successful_episode_count']}`",
            "- Evaluation Chain calls: `0`",
            "- Formal Log Bootstrap: enabled and provenance-recorded",
            "- Historical signed acquisition evidence remains unchanged.",
            "",
        )
    )
    (output / "ROUND510_ACTIVE_RESULTS.md").write_text(results, encoding="utf-8")

    descriptors = build_descriptors(output)
    manifest = {
        "schema_version": 1,
        "draft_only": False,
        "canonical_task": NEW_TASK,
        "artifacts": [item.to_dict() for item in descriptors],
    }
    (output / "active_artifacts.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "active_artifact_count": len(descriptors),
                "output_root": str(output),
                "source_commit": args.source_commit,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
