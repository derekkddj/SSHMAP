import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch, Mock
from argparse import Namespace
from modules.graphdb import GraphDB
from modules.SSHSessionManager import SSHSessionManager
from modules.credential_store import CredentialStore
from modules.SSHSession import SSHSession


class TestStartFromOption:
    """Tests for the --start-from option"""

    def test_start_from_argument_in_parser(self):
        """Test that --start-from argument is properly defined in the parser"""
        # We can test this by checking the SSHMAP.py main() function
        import subprocess
        import os
        # Get the project root directory dynamically
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        result = subprocess.run(
            ['python3', 'SSHMAP.py', '--help'],
            cwd=project_root,
            capture_output=True,
            text=True
        )
        assert '--start-from' in result.stdout
        assert 'Start scanning from a specific remote hostname' in result.stdout

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
