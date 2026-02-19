import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from sshmap_execute import execute_command_on_host
import argparse

@pytest.mark.asyncio
async def test_execute_command_passes_proxy():
    # Mock dependencies
    mock_session_manager_cls = MagicMock()
    mock_session_manager = MagicMock()
    mock_session_manager_cls.return_value = mock_session_manager
    mock_session_manager.get_session = AsyncMock(return_value=None) # Return None to stop execution early
    
    mock_graph = MagicMock()
    mock_cred_store = MagicMock()
    
    with patch("sshmap_execute.SSHSessionManager", mock_session_manager_cls), \
         patch("sshmap_execute.graph", mock_graph), \
         patch("sshmap_execute.sshmap_logger", MagicMock()):
         
        # Mock args
        args = argparse.Namespace(
            command="id",
            quiet=False,
            no_store=True,
            output="output",
            proxy="socks5://127.0.0.1:9050"
        )
        
        # Execute
        await execute_command_on_host(
            args,
            "192.168.1.1",
            "localhost",
            mock_cred_store,
            None
        )
        
        # Verify SSHSessionManager was initialized with proxy_url
        mock_session_manager_cls.assert_called_once_with(
            graphdb=mock_graph,
            credential_store=mock_cred_store,
            proxy_url="socks5://127.0.0.1:9050"
        )
