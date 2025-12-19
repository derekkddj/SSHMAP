import pytest
import asyncio
import asyncssh
from unittest.mock import AsyncMock, MagicMock, patch
from modules.SSHSession import SSHSession


@pytest.mark.asyncio
class TestSSHSession:
    @patch('modules.SSHSession.CONFIG', {"scan_timeout": 5})
    async def test_init(self):
        session = SSHSession("127.0.0.1", "user", password="pass", port=22)
        assert session.host == "127.0.0.1"
        assert session.user == "user"
        assert session.password == "pass"
        assert session.port == 22
        assert session.connection is None
        assert session.remote_hostname is None

    @patch('modules.SSHSession.asyncssh.connect', new_callable=AsyncMock)
    @patch('modules.SSHSession.get_remote_hostname', new_callable=AsyncMock)
    @patch('modules.SSHSession.CONFIG', {"scan_timeout": 5})
    async def test_connect_direct_password_success(self, mock_get_hostname, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_get_hostname.return_value = "remotehost"

        session = SSHSession("127.0.0.1", "user", password="pass")
        result = await session.connect()

        assert result is True
        assert session.connection == mock_conn
        assert session.remote_hostname == "remotehost"
        mock_connect.assert_called_once()
        args = mock_connect.call_args
        assert args[1]['username'] == "user"
        assert args[1]['password'] == "pass"
        assert args[1]['port'] == 22

    @patch('modules.SSHSession.asyncssh.connect', new_callable=AsyncMock)
    @patch('modules.SSHSession.get_remote_hostname', new_callable=AsyncMock)
    @patch('modules.SSHSession.CONFIG', {"scan_timeout": 5})
    async def test_connect_jumper_key_success(self, mock_get_hostname, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_get_hostname.return_value = "remotehost"

        jumper = MagicMock()
        jumper.get_connection.return_value = MagicMock()
        jumper.get_host.return_value = "jumphost"
        jumper.get_remote_hostname.return_value = "jumphost"
        key_objects = {"key": MagicMock()}

        session = SSHSession("127.0.0.1", "user", key_filename="key", jumper=jumper, key_objects=key_objects)
        result = await session.connect()

        assert result is True
        mock_connect.assert_called_once()
        args = mock_connect.call_args
        assert args[1]['tunnel'] == jumper.get_connection.return_value
        assert args[1]['client_keys'] == [key_objects["key"]]

    @patch('modules.SSHSession.asyncssh.connect', side_effect=asyncssh.PermissionDenied)
    @patch('modules.SSHSession.CONFIG', {"scan_timeout": 5})
    async def test_connect_permission_denied(self, mock_connect):
        session = SSHSession("127.0.0.1", "user", password="pass")
        result = await session.connect()

        assert result is False
        assert session.connection is None

    async def test_exec_command(self):
        session = SSHSession("127.0.0.1", "user")
        session.connection = MagicMock()
        session.connection.run = AsyncMock()
        session.connection.run.return_value.stdout = "output"

        result = await session.exec_command("ls")

        assert result == "output"
        session.connection.run.assert_called_once_with("ls")

    async def test_exec_command_not_connected(self):
        session = SSHSession("127.0.0.1", "user")
        session.connection = None

        with pytest.raises(ValueError, match="SSH connection is not established"):
            await session.exec_command("ls")

    async def test_close(self):
        session = SSHSession("127.0.0.1", "user")
        session.connection = MagicMock()
        session.connection.close = MagicMock()
        session.connection.wait_closed = AsyncMock()

        await session.close()

        session.connection.close.assert_called_once()
        session.connection.wait_closed.assert_called_once()

    async def test_is_connected_true(self):
        session = SSHSession("127.0.0.1", "user")
        session.connection = MagicMock()
        process_mock = MagicMock()
        process_mock.wait = AsyncMock()
        process_mock.exit_status = 0
        session.connection.create_process = AsyncMock(return_value=process_mock)

        result = await session.is_connected()

        assert result is True

    async def test_is_connected_false(self):
        session = SSHSession("127.0.0.1", "user")
        session.connection = MagicMock()
        session.connection.create_process = AsyncMock(side_effect=Exception("error"))

        result = await session.is_connected()

        assert result is False

    async def test_getters(self):
        jumper = MagicMock()
        session = SSHSession("127.0.0.1", "user", jumper=jumper)
        session.remote_hostname = "remote"

        assert session.get_connection() is None
        assert session.get_host() == "127.0.0.1"
        assert session.get_remote_hostname() == "remote"
