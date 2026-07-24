import json
from dataclasses import replace

import numpy as np
import pytest

from dc3pa.contracts import Action, AgentState, Plan, PlanStep
from dc3pa.experiments.round513_collection import (
    CHRMLiteBilateralRetrievalPolicyV4_1,
    CHRMLitePlannerOutputSchemaV4_1,
    CHRMLiteRuleTypeRegistryV4_1,
    default_rule_definitions,
)
from dc3pa.experiments.round513_instrumentation import (
    AtomicDecisionStoreV4_1,
    ControllerReceiptV4_1,
    DecisionRecordV4_1,
    OneCallPlannerV4_1,
    PlannerOutputError,
    PreExecutionRecordV4_1,
    StateEvidenceV4_1,
    TrackERunBindingV4_1,
    bilateral_retrieve_v4_1,
    deterministic_record_id,
    extract_knowledge_features_v4_1,
    join_step_outcome_v4_1,
)
from dc3pa.memory.multimodal_memory import MultimodalMemory, SceneObservation, SuccessfulEpisode


class Provider:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def complete(self, prompt):
        assert "PRE_EXECUTION_STATE" in prompt
        self.calls += 1
        return self.response


def _planner_response(confidence="likely"):
    return json.dumps(
        {
            "subgoal": "find a tree",
            "action": {"name": "find", "arguments": {"obj": "tree"}},
            "confidence": confidence,
            "failure_mode": "none",
        }
    )


@pytest.mark.parametrize(
    "confidence",
    ["very_unlikely", "unlikely", "uncertain", "likely", "very_likely"],
)
def test_one_call_planner_parses_all_levels_in_same_generation(confidence):
    provider = Provider(_planner_response(confidence))
    schema = CHRMLitePlannerOutputSchemaV4_1(source_commit="a" * 40).with_computed_id()
    planner = OneCallPlannerV4_1(provider, schema)
    plan = planner.plan("find tree", AgentState(task="find tree"))
    assert provider.calls == 1
    assert plan.steps[0].metadata["v4_1_confidence"] == confidence
    assert plan.steps[0].metadata["v4_1_same_generation"] is True
    assert plan.steps[0].actions[0].args == {"obj": "tree"}


def test_one_call_planner_prompts_with_its_bound_output_schema():
    class CapturingProvider:
        def __init__(self):
            self.prompt = ""

        def complete(self, prompt):
            self.prompt = prompt
            return _planner_response()

    provider = CapturingProvider()
    schema = CHRMLitePlannerOutputSchemaV4_1(
        source_commit="a" * 40,
        output_schema={"bound_schema_marker": "controller-args-v1"},
    ).with_computed_id()
    OneCallPlannerV4_1(provider, schema).plan(
        "find tree",
        AgentState(task="find tree"),
    )
    assert '"bound_schema_marker": "controller-args-v1"' in provider.prompt


def test_malformed_confidence_is_audited_without_hidden_retry():
    provider = Provider(_planner_response("0.9"))
    schema = CHRMLitePlannerOutputSchemaV4_1(source_commit="a" * 40).with_computed_id()
    planner = OneCallPlannerV4_1(provider, schema)
    with pytest.raises(PlannerOutputError):
        planner.plan("find tree", AgentState(task="find tree"))
    assert provider.calls == 1
    assert planner.malformed_audits[0]["retry_performed"] is False


def test_baselines_use_the_same_planner_schema_and_may_ignore_confidence():
    schema = CHRMLitePlannerOutputSchemaV4_1(source_commit="a" * 40).with_computed_id()
    first = OneCallPlannerV4_1(Provider(_planner_response()), schema)
    second = OneCallPlannerV4_1(Provider(_planner_response()), schema)
    assert first.schema.schema_id == second.schema.schema_id
    assert first.schema.prompt_id == second.schema.prompt_id
    assert first.schema.parser_id == second.schema.parser_id


def _rule_registry():
    return CHRMLiteRuleTypeRegistryV4_1(
        source_commit="a" * 40,
        dependency_schema_id="d" * 64,
        rules=default_rule_definitions(),
    ).with_computed_id()


def test_knowledge_hard_soft_split_and_no_soft_semantics():
    registry = _rule_registry()
    hard_conflict = extract_knowledge_features_v4_1(
        registry,
        "craft",
        {
            "mechanics.action_schema": (True, True, {}),
            "controller.craft_material_quantity": (False, True, {}),
            "controller.craft_platform_access": (True, True, {}),
            "memory.verified_dependency": (True, True, {}),
        },
    )
    assert hard_conflict.h == 0
    assert "controller.craft_material_quantity" not in hard_conflict.soft_rule_ids
    assert hard_conflict.k == 1.0 and hard_conflict.u == 1

    partial = extract_knowledge_features_v4_1(
        registry,
        "find",
        {
            "mechanics.action_schema": (True, True, {}),
            "environment.target_visibility": (False, True, {}),
        },
    )
    assert partial.h == 1 and partial.k == 0.0 and partial.u == 1
    no_soft = extract_knowledge_features_v4_1(
        registry,
        "find",
        {"mechanics.action_schema": (True, True, {})},
    )
    assert (no_soft.k, no_soft.u) == (0.0, 0)
    assert "ambiguous.recipe_necessity" not in no_soft.soft_rule_ids


def _scene_plan(action):
    return Plan(task="task", steps=[PlanStep(actions=[action])])


def _memory_with_scenes(tmp_path, positive=4, negative=4):
    root = tmp_path / "memory"
    with MultimodalMemory(root) as memory:
        for index in range(positive + negative):
            action = (
                Action("find", {"obj": "tree"})
                if index < positive
                else Action("find", {"obj": "stone"})
            )
            episode = SuccessfulEpisode(
                task_name="task",
                plan=_scene_plan(action),
                episode_id=f"episode-{index}",
                scenes=(
                    SceneObservation(
                        description="scene",
                        task_context="task",
                        inventory={},
                        position="0,0,0",
                        image_vector=np.array([1.0, float(index % 2)], dtype=np.float32),
                        metadata={
                            "action_key": (
                                "find:tree" if index < positive else "find:stone"
                            )
                        },
                    ),
                ),
            )
            memory.record_success(episode)
    return MultimodalMemory(root, readonly=True)


def _retrieval_policy():
    return CHRMLiteBilateralRetrievalPolicyV4_1(
        source_commit="a" * 40,
        paper_memory_v5_release_id="p" * 64,
        scene_exemplar_release_id="s" * 64,
        mineclip_policy_id="m" * 64,
    ).with_computed_id()


def test_bilateral_retrieval_top3_ties_repeat_and_no_llm(tmp_path):
    with _memory_with_scenes(tmp_path) as memory:
        kwargs = dict(
            memory=memory,
            state=AgentState(task="task", observation_ref="obs-1"),
            image_vector=np.array([1.0, 0.0], dtype=np.float32),
            action=Action("find", {"obj": "tree"}),
            policy=_retrieval_policy(),
            gamma_minus=-0.1,
            gamma_plus=0.1,
        )
        first = bilateral_retrieve_v4_1(**kwargs)
        second = bilateral_retrieve_v4_1(**kwargs)
    assert len(first.positive) == len(first.negative) == 3
    assert first == second
    assert first.online_llm_calls == 0
    assert [item.exemplar_id for item in first.positive] == sorted(
        [item.exemplar_id for item in first.positive],
        key=lambda item: next(
            (-match.score, match.exemplar_id)
            for match in first.positive
            if match.exemplar_id == item
        ),
    )


@pytest.mark.parametrize("positive,negative", [(2, 4), (4, 2), (0, 4), (4, 0)])
def test_bilateral_undercovered_side_is_unknown(tmp_path, positive, negative):
    with _memory_with_scenes(tmp_path, positive=positive, negative=negative) as memory:
        evidence = bilateral_retrieve_v4_1(
            memory=memory,
            state=AgentState(task="task"),
            image_vector=np.array([1.0, 0.0], dtype=np.float32),
            action=Action("find", {"obj": "tree"}),
            policy=_retrieval_policy(),
            gamma_minus=-0.1,
            gamma_plus=0.1,
        )
    assert evidence.raw_state == "unknown"
    assert evidence.contrast is None


ACTIONS = {
    "find": Action("find", {"obj": "tree"}),
    "move_to": Action("move_to", {"obj": "tree"}),
    "mine": Action("mine", {"obj": "cobblestone", "tool": "wooden pickaxe"}),
    "craft": Action("craft", {"obj": {"stick": 4}, "materials": {"planks": 2}, "platform": None}),
    "fight": Action("fight", {"obj": "cow", "tool": "wooden sword"}),
    "equip": Action("equip", {"obj": "wooden pickaxe"}),
    "dig_down": Action("dig_down", {"y_level": 20, "tool": "stone pickaxe"}),
    "dig_up": Action("dig_up", {"tool": "stone pickaxe"}),
    "apply": Action("apply", {"obj": "soil", "tool": "hoe"}),
}


def _state_pair(name, success):
    base = StateEvidenceV4_1(inventory={})
    if name == "find":
        return base, replace(base, target_visible=success)
    if name == "move_to":
        return replace(base, target_distance=8.0), replace(base, target_distance=2.0 if success else 8.0)
    if name == "mine":
        return base, replace(base, inventory={"cobblestone": 1} if success else {})
    if name == "craft":
        return base, replace(base, inventory={"stick": 4} if success else {})
    if name == "fight":
        return replace(base, target_entity_active=True), replace(base, target_entity_active=not success)
    if name == "equip":
        return base, replace(base, held_item="wooden pickaxe" if success else "air")
    if name == "dig_down":
        return replace(base, y_position=30), replace(base, y_position=20 if success else 30)
    if name == "dig_up":
        return replace(base, y_position=10, underground=True), replace(base, y_position=11 if success else 9, underground=False if success else True)
    return replace(base, object_state="old"), replace(base, object_state="new" if success else "old")


@pytest.mark.parametrize("name", sorted(ACTIONS))
def test_every_action_family_uses_verified_transition_over_controller_boolean(name):
    pre, post = _state_pair(name, True)
    controller = ControllerReceiptV4_1(True, False, {"success": False}, 1, 0.1)
    label = join_step_outcome_v4_1(action=ACTIONS[name], pre=pre, post=post, controller=controller)
    assert label.state == "success" and label.value == 1


@pytest.mark.parametrize("name", sorted(ACTIONS))
def test_every_action_family_scientific_failure_beats_controller_success(name):
    pre, post = _state_pair(name, False)
    controller = ControllerReceiptV4_1(True, True, {"success": True}, 1, 0.1)
    label = join_step_outcome_v4_1(action=ACTIONS[name], pre=pre, post=post, controller=controller)
    assert label.state == "scientific_failure" and label.value == 0


@pytest.mark.parametrize("name", sorted(ACTIONS))
def test_every_action_family_separates_technical_and_ambiguous(name):
    base = StateEvidenceV4_1(inventory={}, inventory_observed=False)
    controller = ControllerReceiptV4_1(True, False, {}, 1, 0.1)
    ambiguous = join_step_outcome_v4_1(action=ACTIONS[name], pre=base, post=base, controller=controller)
    assert ambiguous.state == "ambiguous_unobservable" and ambiguous.value is None
    technical = join_step_outcome_v4_1(
        action=ACTIONS[name],
        pre=base,
        post=replace(base, technical_failure="simulator_disconnected"),
        controller=controller,
    )
    assert technical.state == "technical_failure" and technical.value is None


def _binding():
    return TrackERunBindingV4_1(
        authorization_id="a" * 64,
        authorization_status="approved",
        engineering_smoke_approved=True,
        engineering_only=True,
        campaign_id="campaign",
        source_commit="s" * 40,
        task="find tree",
        terminal_task="find tree",
        split="engineering_smoke",
        group_id="smoke:find-tree",
        seed_commitment="z" * 64,
        run_id="run-1",
        episode_id="episode-1",
        memory_release_id="m" * 64,
        dependency_schema_id="d" * 64,
        rule_registry_id="r" * 64,
        scene_release_id="e" * 64,
        mineclip_policy_id="i" * 64,
        planner_schema_id="p" * 64,
        planner_prompt_id="q" * 64,
        planner_parser_id="x" * 64,
        controller_contract_id="c" * 64,
        evaluator_contract_id="v" * 64,
        budget_profile_id="b" * 64,
        gamma_minus=-0.1,
        gamma_plus=0.1,
    )


def _pre_record(binding):
    action = ACTIONS["find"]
    signature = "find:tree"
    from dc3pa.experiments.round513_instrumentation import (
        BilateralEvidenceV4_1,
        KnowledgeFeaturesV4_1,
    )

    return PreExecutionRecordV4_1(
        record_id=deterministic_record_id(binding, 0, signature),
        binding=binding,
        decision_index=0,
        action=action.to_dict(),
        subgoal="find tree",
        action_signature=signature,
        confidence="likely",
        failure_mode="none",
        same_generation_confidence=True,
        planner_call_count=1,
        pre_state=StateEvidenceV4_1(inventory={}),
        knowledge=KnowledgeFeaturesV4_1((), (), (), (), 1, 0.0, 0),
        environment=BilateralEvidenceV4_1("obs", "h", signature, (), (), (), (), 0.0, 0.0, None, "unknown"),
    )


def test_atomic_records_quarantine_engineering_and_are_idempotent(tmp_path):
    store = AtomicDecisionStoreV4_1(tmp_path / "records")
    pre = _pre_record(_binding())
    assert store.persist_pre(pre) == "created"
    assert store.persist_pre(pre) == "pending_resume"
    label = join_step_outcome_v4_1(
        action=ACTIONS["find"],
        pre=pre.pre_state,
        post=replace(pre.pre_state, target_visible=True),
        controller=ControllerReceiptV4_1(True, True, {}, 1, 0.1),
    )
    record = DecisionRecordV4_1(
        pre=pre,
        post_state=replace(pre.pre_state, target_visible=True),
        controller=ControllerReceiptV4_1(True, True, {}, 1, 0.1),
        label=label,
        engineering_only=True,
        formal_fitting_eligible=False,
    )
    first = store.join_post(record)
    second = store.join_post(record)
    assert first == second
    assert first.parent.name == "quarantine"
    assert not store.should_execute(pre.record_id)
    assert store.persist_pre(pre) == "completed_do_not_relaunch"


def test_unapproved_smoke_binding_fails_before_execution():
    pending = replace(
        _binding(),
        authorization_status="pending_author_approval",
        engineering_smoke_approved=False,
    )
    with pytest.raises(PermissionError):
        pending.require_execution_authorized()
