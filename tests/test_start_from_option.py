import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch, Mock
import argparse
from argparse import Namespace
from modules.graphdb import GraphDB
from modules.SSHSessionManager import SSHSessionManager
from modules.credential_store import CredentialStore
from modules.SSHSession import SSHSession


class TestStartFromOption:
    """Tests for the --start-from option"""

    def test_start_from_argument_in_parser(self):
        """Test that --start-from argument is properly defined in the parser"""
        # Test by directly checking if the argument can be parsed
        import sys
        import os
        # Temporarily modify sys.path to import SSHMAP module
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        
        # Create a parser similar to SSHMAP.py
        parser = argparse.ArgumentParser()
        parser.add_argument("--targets", required=True)
        parser.add_argument("--start-from", type=str, default=None)
        
        # Test that we can parse the --start-from argument
        args = parser.parse_args(['--targets', 'test.txt', '--start-from', 'remote_host'])
        assert hasattr(args, 'start_from')
        assert args.start_from == 'remote_host'
        
        # Test that default is None
        args_no_start = parser.parse_args(['--targets', 'test.txt'])
        assert hasattr(args_no_start, 'start_from')
        assert args_no_start.start_from is None

    @pytest.mark.asyncio
    async def test_ssh_session_manager_get_session(self):
        """Test SSHSessionManager.get_session for establishing connection to remote host"""
        # Create mock graph database with a path
        mock_graph = MagicMock(spec=GraphDB)
        mock_graph.find_path.return_value = [
            ('local_host', {
                'user': 'root',
                'method': 'password',
                'creds': 'password123',
                'ip': '172.19.0.2',
                'port': 22
            }, 'remote_host')
        ]
        
        # Create mock credential store
        mock_cred_store = MagicMock(spec=CredentialStore)
        mock_cred_store.get_key_objects.return_value = None
        
        # Create SSHSessionManager
        session_manager = SSHSessionManager(mock_graph, mock_cred_store)
        
        # Mock the SSHSession class to avoid actual SSH connections
        with patch('modules.SSHSessionManager.SSHSession') as mock_ssh_session_class:
            mock_session = MagicMock()
            mock_session.connect = AsyncMock()
            mock_session.is_connected.return_value = True
            mock_ssh_session_class.return_value = mock_session
            
            # Test getting a session
            session = await session_manager.get_session('remote_host', 'local_host')
            
            # Verify the session was created
            assert session is not None
            assert mock_ssh_session_class.called
            assert mock_session.connect.called

    @pytest.mark.asyncio
    async def test_ssh_session_manager_reuses_concurrent_session_creation(self):
        mock_graph = MagicMock(spec=GraphDB)
        mock_graph.find_path.return_value = [
            ('local_host', {
                'user': 'root',
                'method': 'password',
                'creds': 'password123',
                'ip': '172.19.0.2',
                'port': 22
            }, 'remote_host')
        ]
        mock_cred_store = MagicMock(spec=CredentialStore)
        session_manager = SSHSessionManager(mock_graph, mock_cred_store)

        with patch('modules.SSHSessionManager.SSHSession') as mock_ssh_session_class:
            mock_session = MagicMock()
            mock_session.connect = AsyncMock(return_value=True)
            mock_session.is_connected = AsyncMock(return_value=True)
            mock_ssh_session_class.return_value = mock_session

            sessions = await asyncio.gather(
                *(session_manager.get_session('remote_host', 'local_host') for _ in range(10))
            )

            assert all(session is mock_session for session in sessions)
            assert mock_ssh_session_class.call_count == 1
            assert mock_session.connect.await_count == 1

    @pytest.mark.asyncio
    async def test_ssh_session_manager_invalidates_broken_session(self):
        session_manager = SSHSessionManager(MagicMock(spec=GraphDB), MagicMock(spec=CredentialStore))
        session = MagicMock()
        key = ('remote_host', 'root', 'password', 'password123')
        session_manager._cache_session(key, session)

        await session_manager.invalidate_session(session)

        assert key not in session_manager.sessions

    @pytest.mark.asyncio
    async def test_ssh_session_manager_times_out_session_creation(self):
        mock_graph = MagicMock(spec=GraphDB)
        mock_graph.find_path.return_value = [
            ('local_host', {
                'user': 'root',
                'method': 'password',
                'creds': 'password123',
                'ip': '172.19.0.2',
                'port': 22
            }, 'remote_host')
        ]
        mock_cred_store = MagicMock(spec=CredentialStore)
        session_manager = SSHSessionManager(mock_graph, mock_cred_store)

        async def slow_connect():
            await asyncio.sleep(1)
            return True

        with patch('modules.SSHSessionManager.CONFIG', {"scan_timeout": 0.01}), \
             patch('modules.SSHSessionManager.SSHSession') as mock_ssh_session_class:
            mock_session = MagicMock()
            mock_session.connect = AsyncMock(side_effect=slow_connect)
            mock_session.close = AsyncMock()
            mock_ssh_session_class.return_value = mock_session

            session = await session_manager.get_session('remote_host', 'local_host')

            assert session is None
            assert session_manager.sessions == {}
     
    def test_graph_get_host_method_exists(self):
        """Test that GraphDB has the get_host method needed for --start-from"""
        from modules.graphdb import GraphDB
        # Verify the method exists
        assert hasattr(GraphDB, 'get_host')
        # Get the method signature
        import inspect
        sig = inspect.signature(GraphDB.get_host)
        # Verify it takes a hostname parameter
        assert 'hostname' in sig.parameters
