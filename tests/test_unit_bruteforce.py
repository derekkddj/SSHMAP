import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from modules.bruteforce import try_single_credential, try_all, Result
from modules.credential_store import Credential
from modules.SSHSession import SSHSession


class TestResult:
    def test_result_init(self, mock_ssh_session):
        ssh = mock_ssh_session()
        result = Result("user", "password", ssh, "pass")
        assert result.user == "user"
        assert result.method == "password"
        assert result.ssh_session == ssh
        assert result.creds == "pass"

    def test_get_ssh_connection(self, mock_ssh_session):
        ssh = mock_ssh_session()
        result = Result("user", "password", ssh, "pass")
        assert result.get_ssh_connection() == ssh


@pytest.mark.asyncio
class TestTrySingleCredential:
    @patch('modules.bruteforce.CONFIG', {"scan_timeout": 5})
    async def test_password_success(self, mocker, mock_ssh_session, dummy_store):
        # Mock SSHSession.connect to succeed
        ssh_mock = mock_ssh_session(connected=True)
        mocker.patch('modules.bruteforce.SSHSession', return_value=ssh_mock)
        mocker.patch.object(dummy_store, 'store', new_callable=AsyncMock)
        ssh_mgr_mock = MagicMock()
        ssh_mgr_mock.add_session = AsyncMock(return_value=ssh_mock)

        cred = Credential("127.0.0.1", "22", "root", "root", "password")
        result = await try_single_credential("127.0.0.1", 22, cred, credential_store=dummy_store, ssh_session_manager=ssh_mgr_mock)

        assert result is not None
        assert result.user == "root"
        assert result.method == "password"
        dummy_store.store.assert_called_once_with("127.0.0.1", 22, "root", "root", "password")
        ssh_mgr_mock.add_session.assert_called_once()

    @patch('modules.bruteforce.CONFIG', {"scan_timeout": 5})
    async def test_password_failure(self, mocker, mock_ssh_session, dummy_store):
        # Mock SSHSession.connect to fail
        ssh_mock = mock_ssh_session(connected=False)
        mocker.patch('modules.bruteforce.SSHSession', return_value=ssh_mock)
        ssh_mgr_mock = MagicMock()

        cred = Credential("127.0.0.1", "22", "root", "wrong", "password")
        result = await try_single_credential("127.0.0.1", 22, cred, credential_store=dummy_store, ssh_session_manager=ssh_mgr_mock)

        assert result is None

    @patch('modules.bruteforce.CONFIG', {"scan_timeout": 5})
    async def test_keyfile_success(self, mocker, mock_ssh_session, dummy_store):
        ssh_mock = mock_ssh_session(connected=True)
        mocker.patch('modules.bruteforce.SSHSession', return_value=ssh_mock)
        mocker.patch.object(dummy_store, 'store', new_callable=AsyncMock)
        ssh_mgr_mock = MagicMock()
        ssh_mgr_mock.add_session = AsyncMock(return_value=ssh_mock)

        cred = Credential("127.0.0.1", "22", "root", "/path/to/key", "keyfile")
        result = await try_single_credential("127.0.0.1", 22, cred, credential_store=dummy_store, ssh_session_manager=ssh_mgr_mock)

        assert result is not None
        assert result.method == "keyfile"
        dummy_store.store.assert_called_once_with("127.0.0.1", 22, "root", "/path/to/key", "keyfile")

    @patch('modules.bruteforce.CONFIG', {"scan_timeout": 0.001})  # Short timeout
    async def test_timeout(self, mocker, mock_ssh_session, dummy_store):
        ssh_mock = mock_ssh_session(connected=True)
        ssh_mock.connect = AsyncMock(side_effect=asyncio.TimeoutError)
        mocker.patch('modules.bruteforce.SSHSession', return_value=ssh_mock)
        ssh_mgr_mock = MagicMock()

        cred = Credential("127.0.0.1", "22", "root", "root", "password")
        result = await try_single_credential("127.0.0.1", 22, cred, credential_store=dummy_store, ssh_session_manager=ssh_mgr_mock)

        assert result is None


@pytest.mark.asyncio
class TestTryAll:
    @patch('modules.bruteforce.CONFIG', {"scan_timeout": 5})
    async def test_try_all_with_success(self, mocker, mock_ssh_session, dummy_store):
        ssh_mock = mock_ssh_session(connected=True)
        mocker.patch('modules.bruteforce.SSHSession', return_value=ssh_mock)
        mocker.patch.object(dummy_store, 'store', new_callable=AsyncMock)
        ssh_mgr_mock = MagicMock()
        ssh_mgr_mock.add_session = AsyncMock(return_value=ssh_mock)

        # Mock get_credentials_host_and_bruteforce to return one cred
        mocker.patch.object(dummy_store, 'get_credentials_host_and_bruteforce', return_value=[Credential("127.0.0.1", "22", "root", "root", "password")])

        results = await try_all("127.0.0.1", 22, credential_store=dummy_store, ssh_session_manager=ssh_mgr_mock, max_retries=3)

        assert len(results) == 1
        assert results[0].user == "root"

    @patch('modules.bruteforce.CONFIG', {"scan_timeout": 5})
    async def test_try_all_concurrency(self, mocker, mock_ssh_session, dummy_store):
        ssh_mock = mock_ssh_session(connected=False)  # Fail
        mocker.patch('modules.bruteforce.SSHSession', return_value=ssh_mock)
        ssh_mgr_mock = MagicMock()

        creds = [Credential("127.0.0.1", "22", "root", "pass", "password") for _ in range(5)]
        mocker.patch.object(dummy_store, 'get_credentials_host_and_bruteforce', return_value=creds)

        results = await try_all("127.0.0.1", 22, maxworkers=2, credential_store=dummy_store, ssh_session_manager=ssh_mgr_mock, max_retries=3)

        assert len(results) == 0  # All fail</content>
