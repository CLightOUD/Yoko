from backend.tests.evaluation.cases import FIXED_MEMORY_CASES
from backend.tests.evaluation.run_memory_evaluation import evaluate_all_cases


def test_fixed_memory_evaluation_has_15_unique_cases() -> None:
    assert len(FIXED_MEMORY_CASES) == 15
    assert len({case.case_id for case in FIXED_MEMORY_CASES}) == 15


def test_all_fixed_memory_retrieval_cases_pass() -> None:
    result = evaluate_all_cases()

    assert result["case_count"] == 15
    assert result["passed_case_count"] == 15
    assert result["retrieval_case_accuracy"] == 1.0
    assert result["retrieval_recall"] == 1.0
    assert result["irrelevant_retrieval_rate"] == 0.0
    assert result["memory_application_accuracy"] is None
    assert result["incorrect_memory_use_rate"] is None
