#!/usr/bin/env python3
"""End-to-end smoke test for acquisition -> frozen memory -> read-only guard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.memory.acquisition import (  # noqa: E402
    AcquisitionStore,
    LocalSceneCandidate,
    SuccessfulTrajectoryRecord,
)
from dc3pa.memory.snapshot import (  # noqa: E402
    MemorySnapshotManifest,
    ReadOnlyMemoryError,
    SnapshotGuard,
    open_sqlite_readonly,
)


def _write_acquisition(root: Path) -> None:
    store = AcquisitionStore(root)
    episode_id = "round11a-smoke-episode"
    image_path = store.write_rgb_array(
        episode_id=episode_id,
        step_id="craft-pickaxe",
        action_index=0,
        rgb=np.zeros((8, 8, 3), dtype=np.uint8),
    )
    action = {
        "name": "craft",
        "args": {
            "obj": {"wooden pickaxe": 1},
            "materials": {"planks": 3, "stick": 2},
            "platform": "crafting table",
        },
    }
    plan = {
        "task": "obtain wooden pickaxe",
        "plan_id": "round11a-smoke-plan",
        "version": 1,
        "steps": [
            {
                "step_id": "craft-pickaxe",
                "times": 1,
                "expected_outputs": {"wooden pickaxe": 1},
                "metadata": {"local_subgoal": "craft wooden pickaxe"},
                "actions": [action],
            }
        ],
    }
    store.commit_success(
        SuccessfulTrajectoryRecord(
            episode_id=episode_id,
            task_name="obtain wooden pickaxe",
            seed="smoke-seed",
            plan=plan,
            telemetry=(),
            scene_candidates=(
                LocalSceneCandidate(
                    episode_id=episode_id,
                    task_name="obtain wooden pickaxe",
                    plan_id="round11a-smoke-plan",
                    plan_version=1,
                    step_id="craft-pickaxe",
                    step_index=0,
                    action_index=0,
                    local_subgoal="craft wooden pickaxe",
                    action=action,
                    image_path=image_path,
                    pre_inventory={
                        "planks": 3,
                        "stick": 2,
                        "crafting table": 1,
                    },
                ),
            ),
        )
    )


def _build(acquisition_root: Path, output_root: Path) -> None:
    script = ROOT / "scripts_dc3pa" / "build_frozen_memory.py"
    command = [
        sys.executable,
        str(script),
        "--acquisition-root",
        str(acquisition_root),
        "--output-root",
        str(output_root),
        "--source-commit",
        "round11a-smoke",
        "--min-dependency-support",
        "1",
        "--development-encoders",
        "--reset-output",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        print(completed.stdout)
        print(completed.stderr, file=sys.stderr)
        raise RuntimeError(f"frozen memory builder failed: {completed.returncode}")


def run_smoke(work_root: Path) -> dict[str, object]:
    acquisition_root = work_root / "acquisition"
    snapshot_root = work_root / "snapshot"
    _write_acquisition(acquisition_root)
    _build(acquisition_root, snapshot_root)

    manifest_path = snapshot_root / "snapshot_manifest.json"
    db_path = snapshot_root / "memory.sqlite3"
    manifest = MemorySnapshotManifest.from_json(manifest_path)
    if manifest.schema_version < 2:
        raise AssertionError("snapshot manifest must protect external assets")
    if not manifest.asset_files:
        raise AssertionError("snapshot manifest contains no protected assets")
    wal_sidecar = Path(f"{db_path}-wal")
    if wal_sidecar.exists() and wal_sidecar.stat().st_size:
        raise AssertionError(f"non-empty SQLite WAL remains: {wal_sidecar}")

    with SnapshotGuard(manifest):
        with open_sqlite_readonly(db_path) as connection:
            counts = {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in ("episodes", "dependency_edges", "scene_exemplars")
            }
            try:
                connection.execute(
                    "INSERT INTO episodes(episode_id, task_name, success, created_at, metadata_json) "
                    "VALUES ('forbidden', 'x', 1, '', '{}')"
                )
            except sqlite3.OperationalError:
                pass
            else:
                raise AssertionError("read-only snapshot unexpectedly accepted a write")

    asset_relative = sorted(manifest.asset_files)[0]
    asset_path = Path(manifest.snapshot_root) / asset_relative
    original = asset_path.read_bytes()
    asset_path.write_bytes(original + b"tamper")
    mutation_detected = False
    try:
        with SnapshotGuard(manifest):
            pass
    except ReadOnlyMemoryError:
        mutation_detected = True
    finally:
        asset_path.write_bytes(original)
    if not mutation_detected:
        raise AssertionError("SnapshotGuard failed to detect asset mutation")

    return {
        "status": "PASS",
        "manifest_schema": manifest.schema_version,
        "protected_asset_count": len(manifest.asset_files),
        "counts": counts,
        "mutation_detected": mutation_detected,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.work_root:
        args.work_root.mkdir(parents=True, exist_ok=True)
        result = run_smoke(args.work_root.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="dc3pa-round11a-") as temp_dir:
            result = run_smoke(Path(temp_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
