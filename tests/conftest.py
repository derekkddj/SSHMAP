import pytest
from modules.credential_store import CredentialStore


@pytest.fixture
def dummy_store():
    store = CredentialStore()
    store.store("127.0.0.1", 22, "testuser", "testpass", "password")
    return store
