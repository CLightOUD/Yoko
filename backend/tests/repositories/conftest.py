from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.database import Database
from backend.app.repositories import UserRepository


@pytest.fixture
def database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    database.initialize()
    return database


@pytest.fixture
def second_user(database: Database) -> str:
    user_id = "other-user"
    UserRepository(database).create(
        user_id=user_id,
        display_name="其他用户",
        timezone="Asia/Shanghai",
    )
    return user_id
