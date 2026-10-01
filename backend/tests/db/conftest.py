from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from vidituka.config import Settings

BACKEND_DIR = Path(__file__).parents[2]


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = Settings().test_database_url
    if not url:
        if os.environ.get("CI"):
            pytest.fail("VIDITUKA_TEST_DATABASE_URL must be set in CI")
        pytest.skip("set VIDITUKA_TEST_DATABASE_URL to run database tests")

    # full downgrade + upgrade also checks that the migrations work both ways
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> Iterator[sessionmaker[Session]]:
    # everything a test commits is rolled back at the end
    connection = engine.connect()
    transaction = connection.begin()
    yield sessionmaker(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    transaction.rollback()
    connection.close()
