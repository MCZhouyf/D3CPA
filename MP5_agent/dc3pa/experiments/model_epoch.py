"""Short model epochs for experiments using the mutable alias gpt-5.1."""

from __future__ import annotations
import hashlib, json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1
EXPECTED_MODEL = "gpt-5.1"
EXPECTED_EFFORT = "low"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def parse_time(value: str) -> datetime:
    item = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if item.tzinfo is None:
        raise ValueError("Timestamp must contain a timezone")
    return item.astimezone(timezone.utc)


@dataclass(frozen=True)
class EpochPolicy:
    maximum_duration_hours: float = 12.0
    minimum_start_probes: int = 1
    minimum_end_probes: int = 1
    require_interleaved_schedule: bool = True
    hidden_backend_drift_under_same_alias_is_unobservable: bool = True

    def __post_init__(self):
        if self.maximum_duration_hours <= 0:
            raise ValueError("maximum_duration_hours must be positive")
        if self.minimum_start_probes <= 0 or self.minimum_end_probes <= 0:
            raise ValueError("Probe counts must be positive")


@dataclass(frozen=True)
class ProbeObservation:
    observed_at: str
    requested_model: str
    returned_model: str
    profile_id: str
    reasoning_effort: str
    purpose: str
    request_succeeded: bool
    request_text_logged: bool
    response_text_logged: bool
    endpoint_fingerprint: str
    client_context_fingerprint: str
    probe_protocol_id: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    response_id_sha256: str = ""

    def __post_init__(self):
        parse_time(self.observed_at)
        if not self.profile_id or not self.endpoint_fingerprint:
            raise ValueError("Probe identity is incomplete")
        for value in (self.input_tokens, self.output_tokens,
                      self.reasoning_tokens, self.total_tokens):
            if isinstance(value, bool) or value < 0:
                raise ValueError("Token counts must be nonnegative")

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ModelEpoch:
    epoch_name: str
    blueprint_id: str
    source_commit: str
    prompt_hashes: Mapping[str, str]
    model_profile_id: str
    client_context_fingerprint: str
    endpoint_fingerprint: str
    schedule_id: str
    start_probes: tuple[ProbeObservation, ...]
    policy: EpochPolicy = field(default_factory=EpochPolicy)
    end_probes: tuple[ProbeObservation, ...] = ()
    status: str = "open"
    invalid_reasons: tuple[str, ...] = ()
    schema_version: int = SCHEMA_VERSION
    epoch_id: str = ""

    def __post_init__(self):
        if self.status not in {"open", "closed", "invalid"}:
            raise ValueError("Unknown epoch status")
        required = (
            self.epoch_name, self.blueprint_id, self.source_commit,
            self.model_profile_id, self.client_context_fingerprint,
            self.endpoint_fingerprint, self.schedule_id,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Epoch identity is incomplete")
        if self.status == "open" and self.end_probes:
            raise ValueError("Open epoch cannot contain end probes")
        reasons = self.invariant_errors()
        if self.status == "closed" and reasons:
            raise ValueError(f"Closed epoch is invalid: {reasons}")
        if self.status == "invalid" and not self.invalid_reasons:
            raise ValueError("Invalid epoch needs reasons")
        expected = self.compute_id()
        if self.epoch_id and self.epoch_id != expected:
            raise ValueError("Epoch hash mismatch")

    def invariant_errors(self) -> tuple[str, ...]:
        reasons = []
        if len(self.start_probes) < self.policy.minimum_start_probes:
            reasons.append("too few start probes")
        if self.status in {"closed", "invalid"} and (
            len(self.end_probes) < self.policy.minimum_end_probes
        ):
            reasons.append("too few end probes")
        probes = self.start_probes + self.end_probes
        for probe in probes:
            if not probe.request_succeeded:
                reasons.append("probe request failed")
            if probe.requested_model != EXPECTED_MODEL:
                reasons.append("requested model mismatch")
            if probe.returned_model != EXPECTED_MODEL:
                reasons.append("returned model mismatch")
            if probe.profile_id != self.model_profile_id:
                reasons.append("profile mismatch")
            if probe.reasoning_effort != EXPECTED_EFFORT:
                reasons.append("reasoning effort mismatch")
            if probe.endpoint_fingerprint != self.endpoint_fingerprint:
                reasons.append("endpoint mismatch")
            if probe.client_context_fingerprint != self.client_context_fingerprint:
                reasons.append("client context mismatch")
            if probe.request_text_logged or probe.response_text_logged:
                reasons.append("text logging enabled")
        if self.start_probes and self.end_probes:
            start = min(parse_time(item.observed_at) for item in self.start_probes)
            end = max(parse_time(item.observed_at) for item in self.end_probes)
            duration = (end - start).total_seconds() / 3600.0
            if duration < 0:
                reasons.append("epoch end precedes start")
            if duration > self.policy.maximum_duration_hours:
                reasons.append("epoch exceeds maximum duration")
        return tuple(dict.fromkeys(reasons))

    def payload(self):
        value = asdict(self)
        value.pop("epoch_id", None)
        value["prompt_hashes"] = dict(sorted(self.prompt_hashes.items()))
        value["start_probes"] = [item.to_dict() for item in self.start_probes]
        value["end_probes"] = [item.to_dict() for item in self.end_probes]
        value["invalid_reasons"] = list(self.invalid_reasons)
        return value

    def compute_id(self):
        return hashlib.sha256(canonical(self.payload())).hexdigest()

    def with_id(self):
        return replace(self, epoch_id=self.compute_id())

    def to_dict(self):
        value = self.payload()
        value["epoch_id"] = self.epoch_id or self.compute_id()
        return value


def open_epoch(*, epoch_name: str, blueprint_id: str, source_commit: str,
               prompt_hashes: Mapping[str, str], model_profile_id: str,
               client_context_fingerprint: str, endpoint_fingerprint: str,
               schedule_id: str, start_probes: Sequence[ProbeObservation],
               policy: EpochPolicy | None = None) -> ModelEpoch:
    item = ModelEpoch(
        epoch_name=epoch_name,
        blueprint_id=blueprint_id,
        source_commit=source_commit,
        prompt_hashes=dict(prompt_hashes),
        model_profile_id=model_profile_id,
        client_context_fingerprint=client_context_fingerprint,
        endpoint_fingerprint=endpoint_fingerprint,
        schedule_id=schedule_id,
        start_probes=tuple(start_probes),
        policy=policy or EpochPolicy(),
    )
    errors = item.invariant_errors()
    if errors:
        raise ValueError(f"Cannot open epoch: {errors}")
    return item.with_id()


def close_epoch(open_item: ModelEpoch,
                end_probes: Sequence[ProbeObservation]) -> ModelEpoch:
    if open_item.status != "open":
        raise ValueError("Only an open epoch can be closed")
    candidate = replace(open_item, end_probes=tuple(end_probes),
                        status="invalid", invalid_reasons=("validation pending",),
                        epoch_id="")
    errors = candidate.invariant_errors()
    if errors:
        return replace(candidate, invalid_reasons=errors).with_id()
    return replace(candidate, status="closed", invalid_reasons=()).with_id()


def load_probe(path: str | Path) -> ProbeObservation:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    usage = dict(value.pop("usage", {}) or {})
    for name in ("input_tokens", "output_tokens", "reasoning_tokens", "total_tokens"):
        value.setdefault(name, int(usage.get(name, 0) or 0))
    return ProbeObservation(**value)


def load_epoch(path: str | Path) -> ModelEpoch:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    value["start_probes"] = tuple(ProbeObservation(**x)
                                  for x in value["start_probes"])
    value["end_probes"] = tuple(ProbeObservation(**x)
                                for x in value.get("end_probes", ()))
    value["policy"] = EpochPolicy(**value["policy"])
    value["invalid_reasons"] = tuple(value.get("invalid_reasons", ()))
    return ModelEpoch(**value)


def save_immutable(path: str | Path, value: Mapping[str, Any]):
    output = Path(path)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dict(value), indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
