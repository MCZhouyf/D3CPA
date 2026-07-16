"""Author-approved provider model-alias policy.

Some intermediary providers return a backend model identifier that differs
from the requested public model alias. This policy makes that mismatch
auditable without rewriting or discarding the provider-reported identity.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = 1
DECISION = "allow_recorded_provider_model_alias"
ALLOWED_SCOPES = frozenset(
    {
        "model_epoch_probe",
        "natural_readiness",
        "fallback_diagnostic",
        "formal_acquisition",
        "development_experiment",
        "final_evaluation",
    }
)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ProviderModelAliasPolicy:
    policy_name: str
    approved_by: str
    approved_at: str
    approval_record_sha256: str
    requested_model: str = "gpt-5.1"
    decision: str = DECISION
    returned_model_match_required: bool = False
    require_nonempty_returned_model: bool = True
    preserve_requested_and_returned_models: bool = True
    allowed_scopes: tuple[str, ...] = tuple(sorted(ALLOWED_SCOPES))
    schema_version: int = SCHEMA_VERSION
    policy_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported provider model-alias policy schema")
        if self.approved_by != "ZYF":
            raise ValueError("Provider model-alias policy requires ZYF approval")
        if not self.approved_at.strip():
            raise ValueError("Provider model-alias approval timestamp is required")
        if len(self.approval_record_sha256) != 64:
            raise ValueError("Provider model-alias approval SHA256 is invalid")
        if self.requested_model != "gpt-5.1":
            raise ValueError("Provider model-alias policy is bound to gpt-5.1")
        if self.decision != DECISION:
            raise ValueError("Unexpected provider model-alias decision")
        if self.returned_model_match_required:
            raise ValueError("Alias policy must explicitly waive identity equality")
        if not self.require_nonempty_returned_model:
            raise ValueError("Provider must still report a nonempty model identity")
        if not self.preserve_requested_and_returned_models:
            raise ValueError("Provider model identities must remain observable")
        if set(self.allowed_scopes) != ALLOWED_SCOPES:
            raise ValueError("Provider model-alias scope set is incomplete")
        expected = self.compute_policy_id()
        if self.policy_id and self.policy_id != expected:
            raise ValueError("Provider model-alias policy hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("policy_id", None)
        payload["allowed_scopes"] = sorted(self.allowed_scopes)
        return payload

    def compute_policy_id(self) -> str:
        return _sha256(self.payload_without_id())

    def with_id(self) -> "ProviderModelAliasPolicy":
        return replace(self, policy_id=self.compute_policy_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.policy_id else self.with_id()
        payload = item.payload_without_id()
        payload["policy_id"] = item.policy_id
        return payload

    def assert_activation_allowed(self, *, scope: str, requested_model: str) -> None:
        if scope not in self.allowed_scopes:
            raise ValueError(
                f"Provider model-alias policy is forbidden in scope {scope!r}"
            )
        if requested_model != self.requested_model:
            raise ValueError("Provider model-alias requested model mismatch")

    def accepts_returned_model(self, returned_model: str) -> bool:
        return bool(str(returned_model).strip())


def load_provider_model_alias_policy(
    path: str | Path,
    *,
    approval_record: str | Path | None = None,
) -> ProviderModelAliasPolicy:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Provider model-alias policy must be a JSON object")
    values = dict(payload)
    values["allowed_scopes"] = tuple(values.get("allowed_scopes", ()))
    policy = ProviderModelAliasPolicy(**values)
    if not policy.policy_id:
        raise ValueError("Provider model-alias policy must be frozen")
    if approval_record is not None and sha256_file(approval_record) != (
        policy.approval_record_sha256
    ):
        raise ValueError("Provider model-alias approval record SHA256 mismatch")
    return policy


__all__ = [
    "ALLOWED_SCOPES",
    "ProviderModelAliasPolicy",
    "load_provider_model_alias_policy",
    "sha256_file",
]
