import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from sshmap_post import run_module_on_host

@pytest.mark.asyncio
async def test_run_module_passes_proxy():
    # Mock dependencies
    mock_session_manager_cls = MagicMock()
    mock_session_manager = MagicMock()
    mock_session_manager_cls.return_value = mock_session_manager
    mock_session_manager.get_session = AsyncMock(return_value=None) # Return None to stop execution early
    
    mock_registry = MagicMock()
    mock_registry.get_module = MagicMock()
    
    mock_graph = MagicMock()
    mock_cred_store = MagicMock()
    
    with patch("sshmap_post.SSHSessionManager", mock_session_manager_cls), \
         patch("sshmap_post.graph", mock_graph), \
         patch("sshmap_post.sshmap_logger", MagicMock()):
         
        # Execute
        await run_module_on_host(
            module_name="test_module",
            hostname="192.168.1.1",
            local_hostname="localhost",
            credential_store=mock_cred_store,
            output_dir="output",
            registry=mock_registry,
            proxy_url="socks5://127.0.0.1:9050"
        )
        
        # Verify SSHSessionManager was initialized with proxy_url
        mock_session_manager_cls.assert_called_once_with(
            graphdb=mock_graph,
            credential_store=mock_cred_store,
            proxy_url="socks5://127.0.0.1:9050"
        )
