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

    async def test_exec_command_with_stderr(self):
        session = SSHSession("127.0.0.1", "user")
        session.connection = MagicMock()
        session.connection.run = AsyncMock()
        session.connection.run.return_value.stdout = "output"
        session.connection.run.return_value.stderr = "error"
        session.connection.run.return_value.exit_status = 1

        stdout, stderr, exit_status = await session.exec_command_with_stderr("ls")

        assert stdout == "output"
        assert stderr == "error"
        assert exit_status == 1
        session.connection.run.assert_called_once_with("ls")

    @patch('modules.SSHSession.sys')
    @patch('modules.SSHSession.os')
    @patch('modules.SSHSession.termios')
    @patch('modules.SSHSession.tty')
    async def test_interactive_shell_tty(self, mock_tty, mock_termios, mock_os, mock_sys):
        session = SSHSession("127.0.0.1", "user")
        session.connection = MagicMock()
        mock_process = AsyncMock()
        session.connection.create_process = AsyncMock(return_value=mock_process)
        
        # Mock TTY environment
        mock_sys.stdin.isatty.return_value = True
        mock_os.get_terminal_size.return_value = (80, 24)
        mock_os.environ.get.return_value = 'xterm-256color'
        
        await session.interactive_shell()
        
        # Verify creating process with correct args
        session.connection.create_process.assert_called_once()
        call_args = session.connection.create_process.call_args
        assert call_args[1]['term_type'] == 'xterm-256color'
        assert call_args[1]['term_size'] == (80, 24)
        assert call_args[1]['stdin'] == mock_sys.stdin
        
        # Verify TTY handling
        mock_tty.setraw.assert_called_once()
        mock_termios.tcgetattr.assert_called_once()
        mock_termios.tcsetattr.assert_called_once()
        mock_process.wait.assert_awaited_once()
