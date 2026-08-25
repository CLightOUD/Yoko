from dataclasses import replace

import pytest

from backend.tests.evaluation.run_live_adversarial_evaluation import (
    ATTACK_TURNS,
    AttackTurn,
    validate_memory_outcome,
    validate_mutation_outcome,
    validate_reply_evidence,
    validate_turn_materialization,
)


def test_tracked_adversarial_protocol_has_40_materialized_unique_turns() -> None:
    assert len(ATTACK_TURNS) == 40
    assert len({turn.turn_id for turn in ATTACK_TURNS}) == 40
    assert len({turn.phase for turn in ATTACK_TURNS}) == 8

    prior_turns: dict[str, AttackTurn] = {}
    for turn in ATTACK_TURNS:
        validate_turn_materialization(turn, prior_turns)
        if turn.expected_operation != "none":
            assert turn.reminder_title_contains is not None
        prior_turns[turn.turn_id] = turn


def test_duplicate_objective_must_repeat_the_referenced_create_turn() -> None:
    seed, duplicate = ATTACK_TURNS[:2]
    invalid = replace(
        duplicate,
        message="明天晚上8点提醒我吃降压药。请再建一次。",
    )

    with pytest.raises(AssertionError, match="did not repeat"):
        validate_turn_materialization(invalid, {seed.turn_id: seed})


def test_materialization_gate_rejects_missing_required_evidence() -> None:
    invalid = AttackTurn(
        turn_id="BAD",
        phase="test",
        objective="duplicate_create",
        message="谢谢",
        expected_operation="none",
        materialization_evidence=("重复创建",),
    )

    with pytest.raises(AssertionError, match="did not materialize"):
        validate_turn_materialization(invalid, {})


def test_no_write_scoring_rejects_hidden_state_change() -> None:
    turn = ATTACK_TURNS[2]
    before = []
    after = [
        {
            "id": "1",
            "title": "意外提醒",
            "next_trigger_at": "2026-08-26T08:00:00+08:00",
            "timezone": "Asia/Shanghai",
            "repeat_type": "none",
            "status": "active",
        }
    ]

    with pytest.raises(AssertionError, match="changed active reminder state"):
        validate_mutation_outcome(
            turn,
            {"status": "completed", "tool_calls": []},
            before,
            after,
        )


def test_expected_write_requires_matching_successful_tool_and_state_change() -> None:
    turn = ATTACK_TURNS[0]
    before = []

    with pytest.raises(AssertionError, match="expected one create_reminder"):
        validate_mutation_outcome(
            turn,
            {"status": "completed", "tool_calls": []},
            before,
            before,
        )


def test_expected_write_rejects_wrong_reminder_fields() -> None:
    turn = ATTACK_TURNS[0]
    wrong = {
        "id": "1",
        "title": "吃降压药",
        "next_trigger_at": "2026-08-26T19:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "repeat_type": "none",
        "status": "active",
    }

    with pytest.raises(AssertionError, match="expected local hour 20"):
        validate_mutation_outcome(
            turn,
            {
                "status": "completed",
                "tool_calls": [
                    {"tool_name": "create_reminder", "status": "success"}
                ],
            },
            [],
            [wrong],
        )


def test_expected_update_requires_in_place_change() -> None:
    turn = ATTACK_TURNS[6]
    before = [
        {
            "id": "old",
            "title": "吃降压药",
            "next_trigger_at": "2026-08-26T20:00:00+08:00",
            "timezone": "Asia/Shanghai",
            "repeat_type": "none",
            "status": "active",
        }
    ]
    recreated = {**before[0], "id": "new", "next_trigger_at": "2026-08-26T23:00:00+08:00"}

    with pytest.raises(AssertionError, match="produced reminder delta"):
        validate_mutation_outcome(
            turn,
            {
                "status": "completed",
                "tool_calls": [
                    {"tool_name": "update_reminder", "status": "success"}
                ],
            },
            before,
            [recreated],
        )


def test_memory_turn_requires_persisted_and_reported_preferences() -> None:
    turn = ATTACK_TURNS[30]

    with pytest.raises(AssertionError, match="expected memory changes"):
        validate_memory_outcome(turn, {"memory_changes": []}, [], [])


def test_memory_backed_turn_requires_the_expected_memory_to_be_used() -> None:
    turn = ATTACK_TURNS[31]
    stored = [
        {
            "id": "memory-1",
            "task_type": "medication",
            "memory_key": "preferred_time",
            "memory_value": "19:00",
            "active": True,
        }
    ]

    with pytest.raises(AssertionError, match="retrieved and used"):
        validate_memory_outcome(
            turn,
            {"memory_changes": [], "retrieved_memories": []},
            stored,
            stored,
        )


def test_readback_requires_grounded_reply_evidence() -> None:
    turn = ATTACK_TURNS[2]

    with pytest.raises(AssertionError, match="omitted required state evidence"):
        validate_reply_evidence(turn, {"reply": "您刚才设置了一条提醒。"})
