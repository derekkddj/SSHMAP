import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from SSHMAP import handle_target

@pytest.mark.asyncio
async def test_handle_target_skips_port_check_with_proxy():
    # Mock dependencies
    mock_check_open_port = AsyncMock()
    mock_bruteforce = MagicMock()
    mock_bruteforce.try_all = AsyncMock(return_value=[])
    
    with patch("SSHMAP.check_open_port", mock_check_open_port), \
         patch("SSHMAP.bruteforce", mock_bruteforce), \
         patch("SSHMAP.graph", MagicMock()), \
         patch("SSHMAP.attempt_store", MagicMock()), \
         patch("SSHMAP.ssh_ports", [22]), \
         patch("SSHMAP.sshmap_logger", MagicMock()):  # Mock logger to avoid clutter
        
        # Test case 1: Proxy IS provided
        await handle_target(
            target="192.168.1.1",
            maxworkers_ssh=10,
            credential_store=MagicMock(),
            current_depth=1,
            proxy_url="socks5://localhost:9050"
        )
        
        # Verify check_open_port was NOT called (short-circuit)
        mock_check_open_port.assert_not_called()
        
        # Verify bruteforce WAS called
        mock_bruteforce.try_all.assert_called_once()
        
        # Reset mocks
        mock_check_open_port.reset_mock()
        mock_bruteforce.try_all.reset_mock()
        
        # Test case 2: Proxy is NOT provided (and depth=1)
        mock_check_open_port.return_value = True # Port is open
        
        await handle_target(
            target="192.168.1.1",
            maxworkers_ssh=10,
            credential_store=MagicMock(),
            current_depth=1,
            proxy_url=None
        )
        
        # Verify check_open_port WAS called
        mock_check_open_port.assert_called_once()
        mock_bruteforce.try_all.assert_called_once()
