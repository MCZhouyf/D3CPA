#!/usr/bin/env python3
"""Run the frozen Round 5.11 train/tune assignments on real MineDojo."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
DEVELOPMENT_MAX_EXPLORE_STEPS = 60


def _load(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _stage6_environment(
    *, seed: str | int, base: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Bind legacy exploration to the frozen development episode budget."""
    env = dict(os.environ if base is None else base)
    env["PYTHONHASHSEED"] = str(seed)
    env["DC3PA_WORLD_SEED"] = str(seed)
    env["DC3PA_SIM_SEED"] = str(seed)
    env["DC3PA_MAX_EXPLORE_STEPS"] = str(DEVELOPMENT_MAX_EXPLORE_STEPS)
    env["MP5_DISABLE_MEMORY"] = "1"
    env["DC3PA_LEGACY_TASK_HACKS"] = "0"
    return env


def _run_stage6_process(
    command: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    output: Any,
    timeout_seconds: float,
) -> int:
    """Run one episode and terminate its complete Unix process group on timeout."""
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=dict(env),
        stdout=output,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        return process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        # SIGINT gives Stage 6 and MineDojo a chance to run their normal cleanup.
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        return 124


def _task_path(task_root: Path, task: str) -> Path:
    filename = "_".join(task.strip().lower().split()) + ".json"
    path = (task_root / filename).resolve()
    path.relative_to(task_root.resolve())
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _formal_task_spec_path(spec_root: Path, task: str) -> Path:
    return _task_path(spec_root, task)


def _write_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _attempt_id(collection_id: str, group_id: str, attempt: int) -> str:
    return "r511-" + _sha(
        {"collection_id": collection_id, "group_id": group_id, "attempt": attempt}
    )[:24]


def _load_existing_attempt_summary(
    path: Path, *, run_id: str, attempt: int
) -> Mapping[str, Any] | None:
    """Validate a completed attempt so interrupted campaigns can resume safely."""
    if not path.is_file():
        return None
    payload = _load(path)
    if str(payload.get("run_id", "")) != run_id:
        raise ValueError(f"Existing attempt summary/run ID mismatch: {path}")
    if payload.get("attempt") != attempt:
        raise ValueError(f"Existing attempt summary/index mismatch: {path}")
    return payload


def _validate_assignments(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    assignments = payload.get("assignments", ())
    if not isinstance(assignments, list) or not assignments:
        raise ValueError("Mounted development assignment list is empty")
    result = []
    seen_groups: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    for item in assignments:
        if not isinstance(item, Mapping):
            raise ValueError("Development assignment is not an object")
        role = str(item.get("role", ""))
        task = str(item.get("task", ""))
        seed = str(item.get("seed", ""))
        group_id = str(item.get("group_id", ""))
        if role not in {"dev_train", "dev_tune"}:
            raise ValueError("Mounted assignments contain protected holdout data")
        if task == "mine sand":
            raise ValueError("Mounted assignments contain superseded mine sand")
        if not all((task, seed, group_id, str(item.get("difficulty", "")))):
            raise ValueError("Development assignment identity is incomplete")
        if group_id in seen_groups or (task, seed) in seen_pairs:
            raise ValueError("Mounted assignments are not unique")
        seen_groups.add(group_id)
        seen_pairs.add((task, seed))
        result.append(item)
    return sorted(result, key=lambda item: int(item["sequence_index"]))


def _stage6_command(
    *,
    args: argparse.Namespace,
    assignment: Mapping[str, Any],
    run_binding: Path,
    records: Path,
    trace: Path,
    receipt: Path,
    bootstrap_output: Path,
) -> list[str]:
    role = str(assignment["role"])
    return [
        "xvfb-run",
        "-a",
        "-s",
        "-screen 0 1920x1080x24",
        str(args.python),
        str(ROOT / "scripts_dc3pa" / "stage6_run_minecraft.py"),
        "--mode",
        "reasoning_only",
        "--model-profile",
        "gpt51_reference",
        "--provider-model-alias-policy",
        str(args.provider_model_alias_policy),
        "--provider-model-alias-approval",
        str(args.provider_model_alias_approval),
        "--mllm_url",
        os.environ.get("OPENAI_BASE_URL", ""),
        "--task",
        str(_task_path(args.task_root, str(assignment["task"]))),
        "--formal-task-spec",
        str(
            _formal_task_spec_path(
                args.formal_task_spec_root, str(assignment["task"])
            )
        ),
        "--config",
        str(args.stage6_config),
        "--memory-root",
        str(args.memory_root),
        "--trace",
        str(trace),
        "--max-execution-attempts",
        "4",
        "--image-encoder-factory",
        "dc3pa.memory.mineclip_scene_encoder:build_mineclip_image_encoder",
        "--text-encoder-factory",
        "dc3pa.memory.mineclip_scene_encoder:build_mineclip_text_encoder",
        "--encoder-config-json",
        json.dumps(
            {
                "image": {
                    "checkpoint_path": str(args.mineclip_checkpoint),
                    "device": args.mineclip_device,
                },
                "text": {
                    "checkpoint_path": str(args.mineclip_checkpoint),
                    "device": args.mineclip_device,
                },
            },
            sort_keys=True,
        ),
        "--require-environment-score",
        "--real-experiment-phase",
        "development_data_validated",
        "--real-experiment-task",
        str(assignment["task"]),
        "--real-experiment-seed",
        str(assignment["seed"]),
        "--formal-log-bootstrap-policy",
        str(args.bootstrap_policy),
        "--formal-bootstrap-amendment",
        str(args.bootstrap_amendment),
        "--formal-bootstrap-data-binding",
        str(args.bootstrap_binding_train if role == "dev_train" else args.bootstrap_binding_tune),
        "--formal-bootstrap-scope",
        role,
        "--formal-bootstrap-method-id",
        "single_chain_reactive_development",
        "--formal-bootstrap-output-root",
        str(bootstrap_output),
        "--formal-bootstrap-receipt",
        str(receipt),
        "--round511-development-run",
        str(run_binding),
        "--round511-development-records",
        str(records),
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assignments", required=True, type=Path)
    parser.add_argument("--development-input-release", required=True, type=Path)
    parser.add_argument("--bootstrap-policy", required=True, type=Path)
    parser.add_argument("--bootstrap-amendment", required=True, type=Path)
    parser.add_argument("--bootstrap-binding-train", required=True, type=Path)
    parser.add_argument("--bootstrap-binding-tune", required=True, type=Path)
    parser.add_argument("--memory-root", required=True, type=Path)
    parser.add_argument("--mineclip-checkpoint", required=True, type=Path)
    parser.add_argument("--task-root", required=True, type=Path)
    parser.add_argument("--formal-task-spec-root", required=True, type=Path)
    parser.add_argument("--provider-model-alias-policy", required=True, type=Path)
    parser.add_argument("--provider-model-alias-approval", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument(
        "--stage6-config",
        type=Path,
        default=ROOT / "dc3pa" / "configs" / "stage6_closed_loop.json",
    )
    parser.add_argument(
        "--python", type=Path, default=Path(sys.executable).resolve()
    )
    parser.add_argument("--mineclip-device", default="cuda")
    parser.add_argument("--maximum-technical-retries", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--limit", type=int, default=0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.maximum_technical_retries < 0 or args.timeout_seconds <= 0:
        raise ValueError("Retry and timeout limits are invalid")
    if not os.environ.get("OPENAI_API_KEY", ""):
        raise ValueError("OPENAI_API_KEY is required in the environment")
    if not os.environ.get("OPENAI_BASE_URL", ""):
        raise ValueError("OPENAI_BASE_URL is required in the environment")
    assignments = _validate_assignments(_load(args.assignments))
    if args.limit > 0:
        assignments = assignments[: args.limit]
    release = _load(args.development_input_release)
    if not bool(release.get("eligible")):
        raise ValueError("Development Input Release is not eligible")
    source_commit = str(release["source_commit"])
    current_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if source_commit != current_commit:
        raise ValueError("Development Input Release/source commit mismatch")
    protocol_id = str(release["development_protocol_id"])
    collection_id = _sha(
        {
            "source_commit": source_commit,
            "development_input_release_id": release["release_id"],
            "development_protocol_id": protocol_id,
            "assignment_manifest": _sha(assignments),
        }
    )
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    completed = 0
    technical_failures = 0

    for assignment in assignments:
        group_hash = hashlib.sha256(
            str(assignment["group_id"]).encode("utf-8")
        ).hexdigest()[:16]
        group_root = output_root / "runs" / group_hash
        accepted = group_root / "accepted.json"
        if accepted.is_file():
            completed += 1
            continue
        group_root.mkdir(parents=True, exist_ok=True)
        for attempt in range(args.maximum_technical_retries + 1):
            run_id = _attempt_id(collection_id, str(assignment["group_id"]), attempt)
            attempt_root = group_root / f"attempt-{attempt}"
            attempt_root.mkdir(parents=True, exist_ok=True)
            summary_path = attempt_root / "attempt_summary.json"
            existing_summary = _load_existing_attempt_summary(
                summary_path, run_id=run_id, attempt=attempt
            )
            if existing_summary is not None:
                if bool(existing_summary.get("accepted")):
                    raise FileNotFoundError(
                        f"Accepted attempt is missing group marker: {accepted}"
                    )
                technical_failures += 1
                continue
            binding_path = attempt_root / "run_binding.json"
            records = attempt_root / "development_decisions.jsonl"
            trace = attempt_root / "trace.jsonl"
            receipt = attempt_root / "bootstrap_receipt.json"
            console = attempt_root / "console.log"
            bootstrap_output = attempt_root / "bootstrap"
            if not binding_path.exists():
                _write_exclusive(
                    binding_path,
                    {
                        "collection_id": collection_id,
                        "development_input_release_id": release["release_id"],
                        "development_protocol_id": protocol_id,
                        "role": assignment["role"],
                        "group_id": assignment["group_id"],
                        "task": assignment["task"],
                        "seed": str(assignment["seed"]),
                        "difficulty": assignment["difficulty"],
                        "run_id": run_id,
                        "source_commit": source_commit,
                        "paper_memory_v5_release_id": release[
                            "paper_memory_v5_release_id"
                        ],
                        "snapshot_root_sha256": release[
                            "paper_memory_snapshot_root_sha256"
                        ],
                        "bootstrap_policy_id": release[
                            "formal_bootstrap_policy_id"
                        ],
                        "prompt_hash_bundle_id": release["prompt_hash_bundle_id"],
                        "requested_model_name": "gpt-5.1",
                    },
                )
            command = _stage6_command(
                args=args,
                assignment=assignment,
                run_binding=binding_path,
                records=records,
                trace=trace,
                receipt=receipt,
                bootstrap_output=bootstrap_output,
            )
            env = _stage6_environment(seed=assignment["seed"])
            with console.open("ab") as handle:
                returncode = _run_stage6_process(
                    command,
                    cwd=ROOT,
                    env=env,
                    output=handle,
                    timeout_seconds=args.timeout_seconds,
                )
            receipt_payload = _load(receipt) if receipt.is_file() else {}
            accepted_attempt = bool(
                receipt_payload.get("pipeline_pass") and records.is_file()
            )
            _write_exclusive(
                summary_path,
                {
                    "run_id": run_id,
                    "attempt": attempt,
                    "process_return_code": returncode,
                    "pipeline_pass": bool(receipt_payload.get("pipeline_pass")),
                    "task_completed": bool(receipt_payload.get("task_completed")),
                    "records_present": records.is_file(),
                    "accepted": accepted_attempt,
                },
            )
            if accepted_attempt:
                _write_exclusive(
                    accepted,
                    {
                        "run_id": run_id,
                        "attempt": attempt,
                        "role": assignment["role"],
                        "group_id": assignment["group_id"],
                        "task": assignment["task"],
                        "seed": str(assignment["seed"]),
                        "task_completed": bool(receipt_payload.get("task_completed")),
                        "records": str(records.relative_to(output_root)),
                        "receipt": str(receipt.relative_to(output_root)),
                    },
                )
                completed += 1
                break
            technical_failures += 1
        else:
            print(
                json.dumps(
                    {
                        "status": "technical_failure_exhausted",
                        "group_id": assignment["group_id"],
                        "completed": completed,
                    },
                    sort_keys=True,
                )
            )
            return 2

    train_lines: list[str] = []
    tune_lines: list[str] = []
    for accepted in sorted((output_root / "runs").glob("*/accepted.json")):
        payload = _load(accepted)
        record_path = output_root / str(payload["records"])
        lines = [line for line in record_path.read_text(encoding="utf-8").splitlines() if line]
        if payload["role"] == "dev_train":
            train_lines.extend(lines)
        elif payload["role"] == "dev_tune":
            tune_lines.extend(lines)
        else:
            raise ValueError("Accepted run has protected role")
    for name, lines in (
        ("development_decisions_train.jsonl", train_lines),
        ("development_decisions_tune.jsonl", tune_lines),
        ("development_decisions_all.jsonl", train_lines + tune_lines),
    ):
        destination = output_root / name
        if destination.exists():
            existing = destination.read_text(encoding="utf-8").splitlines()
            if existing != lines:
                raise FileExistsError(destination)
        else:
            destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = {
        "collection_id": collection_id,
        "assignment_count": len(assignments),
        "completed_assignment_count": completed,
        "technical_failure_attempt_count": technical_failures,
        "train_decision_count": len(train_lines),
        "tune_decision_count": len(tune_lines),
        "holdout_assignment_count": 0,
        "holdout_accessed": False,
        "final_evaluation_started": False,
    }
    summary_path = output_root / "campaign_summary.json"
    if not summary_path.exists():
        _write_exclusive(summary_path, summary)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
