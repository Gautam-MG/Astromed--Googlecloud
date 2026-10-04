import pytest

import tests.tokens  # noqa: F401  configures the test environment before the app loads
from server import app
from app_core.runtime import reset_services


@pytest.fixture(autouse=True)
def fresh_services():
    reset_services()
    yield


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client
