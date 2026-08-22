from pathlib import Path

import pytest

from backend.app.database import Database
from backend.app.repositories import UserRepository


@pytest.fixture
def database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "services.db")
    database.initialize()
    return database


@pytest.fixture
def other_user(database: Database) -> str:
    UserRepository(database).create(
        user_id="other-user",
        display_name="其他用户",
        timezone="Asia/Shanghai",
    )
    return "other-user"
