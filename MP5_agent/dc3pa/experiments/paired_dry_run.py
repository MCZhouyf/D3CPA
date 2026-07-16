"""Paired natural-readiness and fallback-diagnostic campaign binding."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .log_fallback import assert_readiness_receipts_are_natural


SCHEMA_VERSION = 1


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def campaign_entry_fingerprint(campaign: Mapping[str, Any]) -> str:
    entries = []
    for entry in campaign.get("entries", []):
        entries.append(
            {
                "entry_id": entry.get("entry_id"),
                "group_id": entry.get("group_id"),
                "task": entry.get("task"),
                "seed": str(entry.get("seed", "")),
                "maximum_high_level_steps": entry.get(
                    "maximum_high_level_steps"
                ),
                "maximum_llm_calls": entry.get("maximum_llm_calls"),
                "maximum_replans": entry.get("maximum_replans"),
            }
        )
    entries.sort(
        key=lambda item: (
            str(item["group_id"]),
            str(item["task"]),
            str(item["seed"]),
        )
    )
    return _sha(entries)


@dataclass(frozen=True)
class PairedDryRunProtocol:
    protocol_name: str
    source_commit: str
    blueprint_id: str
    model_profile_id: str
    prompt_hash_bundle_id: str
    natural_campaign_id: str
    diagnostic_campaign_id: str
    natural_entry_fingerprint: str
    diagnostic_entry_fingerprint: str
    natural_fallback_enabled: bool
    diagnostic_fallback_enabled: bool
    fallback_policy_id: str
    natural_results_are_readiness_evidence: bool
    diagnostic_results_are_readiness_evidence: bool
    natural_results_are_paper_performance: bool
    diagnostic_results_are_paper_performance: bool
    schema_version: int = SCHEMA_VERSION
    protocol_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported paired campaign schema")
        required = (
            self.protocol_name,
            self.source_commit,
            self.blueprint_id,
            self.model_profile_id,
            self.prompt_hash_bundle_id,
            self.natural_campaign_id,
            self.diagnostic_campaign_id,
            self.fallback_policy_id,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Paired campaign identity is incomplete")
        if self.natural_campaign_id == self.diagnostic_campaign_id:
            raise ValueError("Natural and diagnostic campaigns must be distinct")
        if self.natural_entry_fingerprint != (
            self.diagnostic_entry_fingerprint
        ):
            raise ValueError("Paired campaigns do not contain identical entries")
        if self.natural_fallback_enabled:
            raise ValueError("Natural readiness campaign must disable fallback")
        if not self.diagnostic_fallback_enabled:
            raise ValueError("Diagnostic campaign must explicitly enable fallback")
        if not self.natural_results_are_readiness_evidence:
            raise ValueError("Natural campaign is the readiness campaign")
        if self.diagnostic_results_are_readiness_evidence:
            raise ValueError("Fallback diagnostics cannot be readiness evidence")
        if self.natural_results_are_paper_performance:
            raise ValueError("Tiny dry run is not paper performance")
        if self.diagnostic_results_are_paper_performance:
            raise ValueError("Fallback diagnostics are not paper performance")
        expected = self.compute_protocol_id()
        if self.protocol_id and self.protocol_id != expected:
            raise ValueError("Paired campaign hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("protocol_id", None)
        return payload

    def compute_protocol_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "PairedDryRunProtocol":
        return replace(self, protocol_id=self.compute_protocol_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.protocol_id else self.with_id()
        payload = item.payload_without_id()
        payload["protocol_id"] = item.protocol_id
        return payload


def load_paired_protocol(path: str | Path) -> PairedDryRunProtocol:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Paired dry-run protocol must be a JSON object")
    values = dict(payload)
    return PairedDryRunProtocol(**values)


@dataclass(frozen=True)
class CampaignFallbackSummary:
    campaign_id: str
    campaign_kind: str
    receipt_count: int
    pipeline_pass_count: int
    task_completed_count: int
    natural_completion_count: int
    fallback_assisted_completion_count: int
    fallback_trigger_count: int
    total_injected_logs: int
    planner_calls: int
    reflection_calls: int
    evaluation_chain_calls: int
    eligible_for_readiness: bool
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_receipts(
    *,
    campaign_id: str,
    campaign_kind: str,
    receipt_payloads: Sequence[Mapping[str, Any]],
) -> CampaignFallbackSummary:
    if campaign_kind not in {"natural_readiness", "fallback_diagnostic"}:
        raise ValueError("Unknown campaign kind")
    if campaign_kind == "natural_readiness":
        assert_readiness_receipts_are_natural(receipt_payloads)

    pipeline = 0
    task_completed = 0
    natural = 0
    assisted = 0
    trigger_count = 0
    injected = 0
    planner = 0
    reflection = 0
    evaluation = 0

    for payload in receipt_payloads:
        if str(payload.get("campaign_id", "")) != campaign_id:
            raise ValueError("Receipt campaign ID mismatch")
        if payload.get("status") == "pipeline_pass":
            pipeline += 1
        metrics = payload.get("fallback_metrics")
        if not isinstance(metrics, Mapping):
            raise ValueError("Receipt is missing fallback_metrics")
        task_completed += int(bool(metrics.get("task_completed", False)))
        natural += int(bool(metrics.get("natural_completion", False)))
        assisted += int(
            bool(metrics.get("fallback_assisted_completion", False))
        )
        trigger_count += int(metrics.get("fallback_trigger_count", 0) or 0)
        injected += int(metrics.get("total_injected_logs", 0) or 0)
        planner += int(metrics.get("planner_calls", 0) or 0)
        reflection += int(metrics.get("reflection_calls", 0) or 0)
        evaluation += int(
            metrics.get("evaluation_chain_calls", 0) or 0
        )

    if task_completed != natural + assisted:
        raise ValueError("Task completion categories do not sum correctly")

    return CampaignFallbackSummary(
        campaign_id=campaign_id,
        campaign_kind=campaign_kind,
        receipt_count=len(receipt_payloads),
        pipeline_pass_count=pipeline,
        task_completed_count=task_completed,
        natural_completion_count=natural,
        fallback_assisted_completion_count=assisted,
        fallback_trigger_count=trigger_count,
        total_injected_logs=injected,
        planner_calls=planner,
        reflection_calls=reflection,
        evaluation_chain_calls=evaluation,
        eligible_for_readiness=campaign_kind == "natural_readiness",
    )


def build_paired_protocol(
    *,
    protocol_name: str,
    source_commit: str,
    blueprint_id: str,
    model_profile_id: str,
    prompt_hash_bundle_id: str,
    natural_campaign: Mapping[str, Any],
    diagnostic_campaign: Mapping[str, Any],
    fallback_policy_id: str,
) -> PairedDryRunProtocol:
    return PairedDryRunProtocol(
        protocol_name=protocol_name,
        source_commit=source_commit,
        blueprint_id=blueprint_id,
        model_profile_id=model_profile_id,
        prompt_hash_bundle_id=prompt_hash_bundle_id,
        natural_campaign_id=str(natural_campaign["campaign_id"]),
        diagnostic_campaign_id=str(diagnostic_campaign["campaign_id"]),
        natural_entry_fingerprint=campaign_entry_fingerprint(
            natural_campaign
        ),
        diagnostic_entry_fingerprint=campaign_entry_fingerprint(
            diagnostic_campaign
        ),
        natural_fallback_enabled=False,
        diagnostic_fallback_enabled=True,
        fallback_policy_id=fallback_policy_id,
        natural_results_are_readiness_evidence=True,
        diagnostic_results_are_readiness_evidence=False,
        natural_results_are_paper_performance=False,
        diagnostic_results_are_paper_performance=False,
    ).with_id()
