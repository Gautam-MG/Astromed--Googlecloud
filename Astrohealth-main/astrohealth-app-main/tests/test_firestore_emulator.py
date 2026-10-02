import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_FIRESTORE_EMULATOR_TESTS"),
    reason="Set RUN_FIRESTORE_EMULATOR_TESTS=1 and FIRESTORE_EMULATOR_HOST to exercise the emulator.",
)


def test_emulator_round_trip():
    from app_core.repository import FirestoreRepository
    from app_core.settings import load_settings

    repository = FirestoreRepository(load_settings())
    assert repository.ping()
    user = repository.get_or_create_user("user_emulator")
    saved = repository.save(user["internal_user_id"], "inputs", "input-1", {"record_type": "input", "status": "processed"})
    loaded = repository.get(user["internal_user_id"], "inputs", "input-1")
    assert loaded["status"] == saved["status"]
    other = repository.get_or_create_user("user_emulator_other")
    assert repository.get(other["internal_user_id"], "inputs", "input-1") is None
