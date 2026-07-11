import pytest

from dc3pa.contracts import AgentState
from dc3pa.reliability import (
    CallableConfidenceProvider,
    VerbalConfidenceStrategy,
    parse_confidence,
)
from tests_dc3pa.helpers_stage3_5 import simple_plan


@pytest.mark.parametrize(
    "raw, expected",
    [
        (0.8, 0.8),
        ("80%", 0.8),
        ({"confidence": 0.7, "reason": "ok"}, 0.7),
        ('```json\n{"confidence": 65, "reason": "uncertain"}\n```', 0.65),
    ],
)
def test_parse_confidence_supported_formats(raw, expected):
    probability, _, _ = parse_confidence(raw)
    assert probability == pytest.approx(expected)


def test_parse_confidence_rejects_bool_and_out_of_range():
    with pytest.raises(ValueError):
        parse_confidence(True)
    with pytest.raises(ValueError):
        parse_confidence(101)


def test_verbal_confidence_cache_avoids_duplicate_provider_calls():
    calls = []

    def provider(request):
        calls.append(request.step.step_id)
        return {"confidence": 0.83, "reason": "concise"}

    plan = simple_plan(1)
    strategy = VerbalConfidenceStrategy(CallableConfidenceProvider(provider))
    state = AgentState(task=plan.task)
    first = strategy.score(plan, 0, state)
    second = strategy.score(plan, 0, state)
    assert first.probability == second.probability == 0.83
    assert calls == [plan.steps[0].step_id]
    assert second.evidence["cache_hit"] is True


def test_provider_failure_can_be_marked_unavailable_or_raised():
    provider = CallableConfidenceProvider(lambda request: (_ for _ in ()).throw(RuntimeError("x")))
    plan = simple_plan(1)
    state = AgentState(task=plan.task)
    unavailable = VerbalConfidenceStrategy(provider, failure_mode="unavailable").score(
        plan, 0, state
    )
    assert unavailable.probability is None
    with pytest.raises(RuntimeError):
        VerbalConfidenceStrategy(provider, failure_mode="raise").score(plan, 0, state)


def test_transient_provider_failure_is_not_cached():
    calls = []

    def provider(request):
        calls.append(request.step.step_id)
        if len(calls) == 1:
            raise RuntimeError("temporary")
        return {"confidence": 0.9, "reason": "recovered"}

    plan = simple_plan(1)
    strategy = VerbalConfidenceStrategy(CallableConfidenceProvider(provider))
    state = AgentState(task=plan.task)
    first = strategy.score(plan, 0, state)
    second = strategy.score(plan, 0, state)
    assert first.probability is None
    assert second.probability == pytest.approx(0.9)
    assert len(calls) == 2
