import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from modules.utils import create_proxy_socket
import socks

def test_create_proxy_socket_socks5():
    with patch("socks.socksocket") as mock_socket_cls:
        mock_socket = MagicMock()
        mock_socket_cls.return_value = mock_socket
        
        proxy_url = "socks5://127.0.0.1:9050"
        target_host = "192.168.1.1"
        target_port = 22
        
        s = create_proxy_socket(proxy_url, target_host, target_port)
        
        mock_socket_cls.assert_called_once()
        mock_socket.set_proxy.assert_called_with(socks.SOCKS5, "127.0.0.1", 9050)
        mock_socket.connect.assert_called_with((target_host, target_port))
        assert s == mock_socket

def test_create_proxy_socket_http():
    with patch("socks.socksocket") as mock_socket_cls:
        mock_socket = MagicMock()
        mock_socket_cls.return_value = mock_socket
        
        proxy_url = "http://proxy.example.com:8080"
        target_host = "192.168.1.1"
        target_port = 22
        
        s = create_proxy_socket(proxy_url, target_host, target_port)
        
        mock_socket.set_proxy.assert_called_with(socks.HTTP, "proxy.example.com", 8080)
        mock_socket.connect.assert_called_with((target_host, target_port))

def test_create_proxy_socket_fail():
    with patch("socks.socksocket") as mock_socket_cls:
        mock_socket = MagicMock()
        mock_socket_cls.return_value = mock_socket
        mock_socket.connect.side_effect = Exception("Connection Refused")
        
        proxy_url = "socks5://127.0.0.1:9050"
        s = create_proxy_socket(proxy_url, "1.1.1.1", 22)
        
        assert s is None

@pytest.mark.asyncio
async def test_ssh_session_connect_via_proxy():
    from modules.SSHSession import SSHSession
    
    with patch("modules.SSHSession.create_proxy_socket") as mock_create_sock, \
         patch("modules.SSHSession.asyncssh.connect", new_callable=AsyncMock) as mock_ssh_connect, \
         patch("modules.SSHSession.get_remote_hostname", new_callable=AsyncMock) as mock_get_hostname:
         
        # Mock dependencies
        mock_sock = MagicMock()
        mock_create_sock.return_value = mock_sock
        mock_get_hostname.return_value = "remote-host"
        
        # Initialize session with proxy
        session = SSHSession(
            host="192.168.1.1",
            user="root",
            password="password",
            proxy_url="socks5://127.0.0.1:9050",
            attempt_id="test-id"
        )
        
        # Connect
        result = await session.connect()
        
        # Verify proxy socket creation
        mock_create_sock.assert_called_with("socks5://127.0.0.1:9050", "192.168.1.1", 22)
        
        # Verify asyncssh connection using the socket
        mock_ssh_connect.assert_called_once()
        _, kwargs = mock_ssh_connect.call_args
        assert kwargs.get("sock") == mock_sock
        assert result is True
