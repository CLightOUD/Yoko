from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from backend.app.database import Database
from backend.app.repositories import UserRepository
from backend.app.schemas import MemoryUpdateRequest
from backend.app.services import MemoryService
from backend.tests.evaluation.cases import (
    FIXED_MEMORY_CASES,
    MemoryEvaluationCase,
)


def identity(memory: Any) -> str:
    return f"{memory.task_type}:{memory.memory_key}"


def evaluate_case(case: MemoryEvaluationCase, database_path: Path) -> dict[str, Any]:
    database = Database(database_path)
    database.initialize()
    users = UserRepository(database)
    service = MemoryService(database)
    if any(item.user_id == "other-user" for item in case.seeds):
        users.create(
            user_id="other-user",
            display_name="其他用户",
            timezone="Asia/Shanghai",
        )

    for item in case.seeds:
        change = service.upsert(
            user_id=item.user_id,
            scope=item.scope,
            task_type=item.task_type,
            memory_key=item.memory_key,
            memory_value=item.memory_value,
            display_text=item.display_text,
            reason="固定评估数据",
        )
        if not item.active:
            service.update(
                change.memory.id,
                MemoryUpdateRequest(user_id=item.user_id, active=False),
            )

    retrieved = service.retrieve(
        user_id="demo-user",
        task_type=case.task_type,
        limit=case.limit,
    )
    actual_identities = tuple(identity(memory) for memory in retrieved)
    actual_values = {identity(memory): memory.memory_value for memory in retrieved}
    expected_values = dict(case.expected_values)
    values_match = all(
        actual_values.get(key) == expected for key, expected in expected_values.items()
    )
    expected_set = set(case.expected_identities)
    actual_set = set(actual_identities)
    unexpected = sorted(actual_set - expected_set)
    missing = sorted(expected_set - actual_set)
    passed = actual_identities == case.expected_identities and values_match
    return {
        "case_id": case.case_id,
        "description": case.description,
        "passed": passed,
        "expected_identities": list(case.expected_identities),
        "actual_identities": list(actual_identities),
        "unexpected_identities": unexpected,
        "missing_identities": missing,
        "expected_values": expected_values,
        "actual_values": actual_values,
    }


def evaluate_all_cases() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix="yoko-memory-eval-") as temp_dir:
        root = Path(temp_dir)
        for case in FIXED_MEMORY_CASES:
            results.append(evaluate_case(case, root / f"{case.case_id}.db"))

    passed = sum(result["passed"] for result in results)
    expected_count = sum(len(result["expected_identities"]) for result in results)
    actual_count = sum(len(result["actual_identities"]) for result in results)
    missing_count = sum(len(result["missing_identities"]) for result in results)
    unexpected_count = sum(len(result["unexpected_identities"]) for result in results)
    relevant_count = expected_count - missing_count
    return {
        "evaluation_version": "memory-retrieval-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "case_count": len(results),
        "passed_case_count": passed,
        "retrieval_case_accuracy": passed / len(results),
        "retrieval_recall": relevant_count / expected_count if expected_count else 1.0,
        "irrelevant_retrieval_rate": (
            unexpected_count / actual_count if actual_count else 0.0
        ),
        "memory_application_accuracy": None,
        "incorrect_memory_use_rate": None,
        "application_metric_limitation": (
            "Agent 尚未集成；当前仅验证规则检索，不能据此推断记忆是否被模型正确使用。"
        ),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the 15 fixed memory cases")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path; otherwise print to stdout.",
    )
    args = parser.parse_args()
    result = evaluate_all_cases()
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output is None:
        print(rendered)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(args.output.resolve())
    return 0 if result["passed_case_count"] == result["case_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
