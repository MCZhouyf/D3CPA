"""Offline analysis for Stage A. Reads JSONL logs; runs no environment.

Produces the four tables Stage A must deliver:

A. substitute scope     which tasks trigger the low-level substitute, per tier,
                        and exactly which items it grants
B. mode symmetry        per-runtime-mode invocation counts and granted items;
                        Option B is only defensible if these are comparable
C. order invariance     per-seed outcome agreement under forward vs reverse
                        traversal, separately for acquire and evaluate_readonly
D. dual population      every headline metric on all tasks and on the subset
                        the substitute never touches

Inputs
------
inventory_writes.jsonl  one record per ``env.set_inventory`` call
                        (see ``inventory_write_logger.InventoryWriteLogger``)
episodes.jsonl          one record per episode, with at least:
                        run_id, task, tier, seed, runtime_mode, memory_mode,
                        traversal ("forward"/"reverse"), success (bool)

Usage
-----
    python -m dc3pa_stage_a.analyze_stage_a \
        --inventory-writes runs/stageA/inventory_writes.jsonl \
        --episodes runs/stageA/episodes.jsonl \
        --output docs/evidence/stage_a/analysis.json \
        --markdown docs/STAGE_A_ANALYSIS.md
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


# --------------------------------------------------------------------------- IO


_SUBSTITUTE_CALLERS = {
    "_fallback_mine_diamond_resource",
    "_fallback_craft_diamond_item",
    "_fallback_craft_wooden_pickaxe",
    "_fallback_craft_bootstrap_item",
    "_fallback_craft_stone_pickaxe",
    "ensure_wooden_bootstrap",
    "_gather_logs",
}


def is_substitute_write(record: Mapping[str, Any]) -> bool:
    """Return True only for a positive controller-level substitute write.

    The logger deliberately records every inventory write, including the normal
    empty-inventory reset at episode start. Scope and symmetry tables must not
    count that reset as a low-level substitute invocation.
    """
    if not (record.get("granted") or {}):
        return False
    caller_chain = record.get("caller_chain")
    if not caller_chain:
        # Legacy/truncated evidence lacks a stack; preserve the package's
        # historical convention that positive grants in such evidence are
        # substitute records. Newly collected Stage A evidence always has one.
        return True
    return any(
        frame.get("function") in _SUBSTITUTE_CALLERS
        for frame in caller_chain
        if isinstance(frame, Mapping)
    )


def read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} is not valid JSON") from exc
    return records


def _episode_key(record: Mapping[str, Any]) -> Tuple[Any, Any, Any, Any]:
    return (
        record.get("task"),
        record.get("seed"),
        record.get("runtime_mode"),
        record.get("traversal"),
    )


# ----------------------------------------------------------------- A. scope


def substitute_scope(
    writes: Sequence[Mapping[str, Any]],
    episodes: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Which tasks the substitute touches, and what it grants."""
    tier_of: Dict[Any, Any] = {}
    for episode in episodes:
        task = episode.get("task")
        if task is not None and task not in tier_of:
            tier_of[task] = episode.get("tier")

    granted_by_task: Dict[Any, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    calls_by_task: Dict[Any, int] = defaultdict(int)
    for write in filter(is_substitute_write, writes):
        task = write.get("task")
        calls_by_task[task] += 1
        for item, quantity in (write.get("granted") or {}).items():
            granted_by_task[task][item] += int(quantity)

    affected = sorted(t for t in calls_by_task if t is not None)
    all_tasks = sorted({e.get("task") for e in episodes if e.get("task") is not None})
    unaffected = [t for t in all_tasks if t not in set(affected)]

    per_tier: Dict[Any, Dict[str, int]] = defaultdict(
        lambda: {"total_tasks": 0, "affected_tasks": 0}
    )
    for task in all_tasks:
        tier = tier_of.get(task)
        per_tier[tier]["total_tasks"] += 1
        if task in set(affected):
            per_tier[tier]["affected_tasks"] += 1

    return {
        "total_tasks": len(all_tasks),
        "affected_tasks": affected,
        "unaffected_tasks": unaffected,
        "affected_task_count": len(affected),
        "affected_fraction": (len(affected) / len(all_tasks)) if all_tasks else 0.0,
        "per_tier": {str(k): v for k, v in sorted(per_tier.items(), key=lambda kv: str(kv[0]))},
        "calls_by_task": {str(k): v for k, v in sorted(calls_by_task.items(), key=lambda kv: str(kv[0]))},
        "granted_by_task": {
            str(task): dict(sorted(items.items()))
            for task, items in sorted(granted_by_task.items(), key=lambda kv: str(kv[0]))
        },
    }


# ------------------------------------------------------------- B. symmetry


def mode_symmetry(
    writes: Sequence[Mapping[str, Any]],
    episodes: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Per-runtime-mode substitute usage.

    Option B rests on the substitute being applied identically to every compared
    method. Code-level symmetry is necessary but not sufficient: if one runtime
    mode produces plans that invoke the substitute more often, it receives more
    free resources, and the internal comparison is confounded.
    """
    episodes_by_mode: Dict[Any, int] = defaultdict(int)
    for episode in episodes:
        episodes_by_mode[episode.get("runtime_mode")] += 1

    calls_by_mode: Dict[Any, int] = defaultdict(int)
    items_by_mode: Dict[Any, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    episodes_with_substitute: Dict[Any, set] = defaultdict(set)
    for write in filter(is_substitute_write, writes):
        mode = write.get("runtime_mode")
        calls_by_mode[mode] += 1
        episodes_with_substitute[mode].add((write.get("task"), write.get("seed")))
        for item, quantity in (write.get("granted") or {}).items():
            items_by_mode[mode][item] += int(quantity)

    per_mode: Dict[str, Any] = {}
    for mode, episode_count in sorted(episodes_by_mode.items(), key=lambda kv: str(kv[0])):
        calls = calls_by_mode.get(mode, 0)
        touched = len(episodes_with_substitute.get(mode, set()))
        per_mode[str(mode)] = {
            "episodes": episode_count,
            "substitute_calls": calls,
            "calls_per_episode": (calls / episode_count) if episode_count else 0.0,
            "episodes_touched": touched,
            "episodes_touched_fraction": (touched / episode_count) if episode_count else 0.0,
            "granted_items": dict(sorted(items_by_mode.get(mode, {}).items())),
        }

    rates = [entry["calls_per_episode"] for entry in per_mode.values()]
    spread = (max(rates) - min(rates)) if rates else 0.0
    max_rate = max(rates) if rates else 0.0
    relative_spread = (spread / max_rate) if max_rate else 0.0

    return {
        "per_mode": per_mode,
        "calls_per_episode_spread": spread,
        "calls_per_episode_relative_spread": relative_spread,
        # Descriptive flag only; the acceptance threshold belongs to the work order.
        "symmetric_within_10pct": relative_spread <= 0.10,
    }


# --------------------------------------------------------- C. order invariance


def order_invariance(episodes: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Forward vs reverse traversal agreement, split by memory_mode.

    Under ``acquire`` the long-term memory accumulates across episodes, so the
    traversal order changes what each seed can read. Under ``evaluate_readonly``
    it cannot, so per-seed outcomes should agree.
    """
    indexed: Dict[Tuple[Any, Any, Any, Any], Any] = {}
    for episode in episodes:
        traversal = episode.get("traversal")
        if traversal not in {"forward", "reverse"}:
            continue
        key = (
            episode.get("memory_mode"),
            episode.get("runtime_mode"),
            episode.get("task"),
            episode.get("seed"),
        )
        indexed[key + (traversal,)] = bool(episode.get("success"))

    by_memory_mode: Dict[Any, Dict[str, Any]] = defaultdict(
        lambda: {"compared": 0, "agreed": 0, "mismatches": []}
    )
    seen: set = set()
    for key in indexed:
        base, traversal = key[:-1], key[-1]
        if base in seen:
            continue
        forward = indexed.get(base + ("forward",))
        reverse = indexed.get(base + ("reverse",))
        if forward is None or reverse is None:
            continue
        seen.add(base)
        memory_mode, runtime_mode, task, seed = base
        bucket = by_memory_mode[memory_mode]
        bucket["compared"] += 1
        if forward == reverse:
            bucket["agreed"] += 1
        else:
            bucket["mismatches"].append(
                {
                    "runtime_mode": runtime_mode,
                    "task": task,
                    "seed": seed,
                    "forward_success": forward,
                    "reverse_success": reverse,
                }
            )

    result: Dict[str, Any] = {}
    for memory_mode, bucket in sorted(by_memory_mode.items(), key=lambda kv: str(kv[0])):
        compared = bucket["compared"]
        result[str(memory_mode)] = {
            "compared_pairs": compared,
            "agreed": bucket["agreed"],
            "agreement_rate": (bucket["agreed"] / compared) if compared else None,
            "mismatches": bucket["mismatches"],
        }
    return result


# ------------------------------------------------------ D. dual population


def dual_population_success(
    episodes: Sequence[Mapping[str, Any]],
    affected_tasks: Iterable[Any],
) -> Dict[str, Any]:
    """Success rate on all tasks and on the substitute-free subset.

    The substitute-free subset is the strongest robustness evidence available
    under Option B: if a conclusion holds there, the substitute is not producing
    it.
    """
    affected = set(affected_tasks)

    def summarise(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        by_mode: Dict[Any, Dict[str, int]] = defaultdict(
            lambda: {"episodes": 0, "successes": 0}
        )
        for row in rows:
            bucket = by_mode[row.get("runtime_mode")]
            bucket["episodes"] += 1
            if row.get("success"):
                bucket["successes"] += 1
        return {
            str(mode): {
                "episodes": bucket["episodes"],
                "successes": bucket["successes"],
                "success_rate": (bucket["successes"] / bucket["episodes"])
                if bucket["episodes"]
                else None,
            }
            for mode, bucket in sorted(by_mode.items(), key=lambda kv: str(kv[0]))
        }

    all_rows = list(episodes)
    clean_rows = [row for row in episodes if row.get("task") not in affected]
    return {
        "all_tasks": summarise(all_rows),
        "substitute_free_tasks": summarise(clean_rows),
        "substitute_free_task_count": len({r.get("task") for r in clean_rows}),
    }


# ----------------------------------------------------------------- reporting


def build_report(
    writes: Sequence[Mapping[str, Any]],
    episodes: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    scope = substitute_scope(writes, episodes)
    return {
        "substitute_scope": scope,
        "mode_symmetry": mode_symmetry(writes, episodes),
        "order_invariance": order_invariance(episodes),
        "dual_population": dual_population_success(episodes, scope["affected_tasks"]),
        "counts": {"inventory_writes": len(writes), "episodes": len(episodes)},
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    scope = report["substitute_scope"]
    symmetry = report["mode_symmetry"]
    order = report["order_invariance"]
    dual = report["dual_population"]

    lines: List[str] = ["# Stage A analysis", ""]

    lines += [
        "## A. Low-level substitute scope",
        "",
        f"- tasks in run: {scope['total_tasks']}",
        f"- tasks touched by the substitute: {scope['affected_task_count']} "
        f"({scope['affected_fraction']:.1%})",
        f"- affected: {', '.join(map(str, scope['affected_tasks'])) or '(none)'}",
        "",
        "| tier | tasks | affected |",
        "| --- | ---: | ---: |",
    ]
    for tier, entry in scope["per_tier"].items():
        lines.append(f"| {tier} | {entry['total_tasks']} | {entry['affected_tasks']} |")
    lines += ["", "| task | calls | granted items |", "| --- | ---: | --- |"]
    for task, calls in scope["calls_by_task"].items():
        granted = scope["granted_by_task"].get(task, {})
        rendered = ", ".join(f"{k}×{v}" for k, v in granted.items()) or "-"
        lines.append(f"| {task} | {calls} | {rendered} |")

    lines += [
        "",
        "## B. Per-mode symmetry",
        "",
        "| runtime mode | episodes | calls | calls/episode | episodes touched |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for mode, entry in symmetry["per_mode"].items():
        lines.append(
            f"| {mode} | {entry['episodes']} | {entry['substitute_calls']} | "
            f"{entry['calls_per_episode']:.3f} | "
            f"{entry['episodes_touched']} ({entry['episodes_touched_fraction']:.1%}) |"
        )
    lines += [
        "",
        f"- calls/episode relative spread: {symmetry['calls_per_episode_relative_spread']:.1%}",
        f"- within 10%: {symmetry['symmetric_within_10pct']}",
    ]

    lines += [
        "",
        "## C. Order invariance",
        "",
        "| memory mode | compared pairs | agreed | agreement |",
        "| --- | ---: | ---: | ---: |",
    ]
    for memory_mode, entry in order.items():
        rate = entry["agreement_rate"]
        rendered = f"{rate:.1%}" if rate is not None else "-"
        lines.append(
            f"| {memory_mode} | {entry['compared_pairs']} | {entry['agreed']} | {rendered} |"
        )

    lines += [
        "",
        "## D. Dual population success rate",
        "",
        "| runtime mode | all tasks | substitute-free tasks |",
        "| --- | ---: | ---: |",
    ]
    modes = sorted(set(dual["all_tasks"]) | set(dual["substitute_free_tasks"]))
    for mode in modes:
        left = dual["all_tasks"].get(mode, {})
        right = dual["substitute_free_tasks"].get(mode, {})

        def fmt(entry: Mapping[str, Any]) -> str:
            rate = entry.get("success_rate")
            if rate is None:
                return "-"
            return f"{rate:.1%} ({entry['successes']}/{entry['episodes']})"

        lines.append(f"| {mode} | {fmt(left)} | {fmt(right)} |")

    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Stage A offline analysis")
    parser.add_argument("--inventory-writes", required=True)
    parser.add_argument("--episodes", required=True)
    parser.add_argument("--output", required=True, help="JSON report path")
    parser.add_argument("--markdown", default=None, help="optional markdown path")
    args = parser.parse_args(argv)

    writes = read_jsonl(args.inventory_writes)
    episodes = read_jsonl(args.episodes)
    report = build_report(writes, episodes)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.markdown:
        markdown = Path(args.markdown)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(render_markdown(report), encoding="utf-8")

    print(json.dumps(report["substitute_scope"], sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
