from backend.app.agent.preferences import (
    classify_task,
    extract_preference,
    extract_preferences,
    normalize_user_text,
)


def test_extracts_long_term_task_and_global_preferences() -> None:
    medication = extract_preference("太晚了，以后服药都在晚上7点提醒")
    walking = extract_preference("以后散步都早上七点半")
    appointment = extract_preference("以后预约都提前30分钟提醒")
    style = extract_preference("以后回答简短一点")

    assert medication is not None and medication.memory_value == "19:00"
    assert walking is not None and walking.memory_value == "07:30"
    assert appointment is not None and appointment.memory_value == "30m"
    assert style is not None and style.memory_value == "concise"


def test_rejects_temporary_or_unclear_preferences() -> None:
    assert extract_preference("今天晚上7点提醒我吃药") is None
    assert extract_preference("这个回答不错") is None
    assert extract_preference("以后不要晚上8点提醒我吃药") is None


def test_long_term_clause_overrides_temporary_context() -> None:
    preference = extract_preference(
        "今天晚上8点吃药太晚了，以后都在晚上7点提醒"
    )

    assert preference is not None
    assert preference.task_type == "medication"
    assert preference.memory_value == "19:00"


def test_classifies_named_medication_as_medication_task() -> None:
    assert classify_task("明天提醒我吃降压药") == "medication"


def test_extracts_multiple_preferences_from_compound_feedback() -> None:
    preferences = extract_preferences(
        "以后回答简短一点，并且服药都在晚上7点提醒，默认使用中文"
    )

    assert [
        (preference.task_type, preference.memory_key, preference.memory_value)
        for preference in preferences
    ] == [
        ("global", "response_style", "concise"),
        ("medication", "preferred_time", "19:00"),
        ("global", "language", "zh-CN"),
    ]


def test_negation_only_skips_the_affected_clause() -> None:
    preferences = extract_preferences(
        "以后回答简短一点，但是不要晚上8点提醒我吃药"
    )

    assert len(preferences) == 1
    assert preferences[0].memory_key == "response_style"


def test_normalization_does_not_rewrite_semantic_typos() -> None:
    text = "  记住， 以后吃降压药都晚丄7典提酲我  "

    assert normalize_user_text(text) == "记住， 以后吃降压药都晚丄7典提酲我"
