import pytest
from unittest.mock import MagicMock, patch
from modules.graphdb import GraphDB


class TestConnectionAttempts:
    """Test the connection attempt tracking functionality"""

    @pytest.fixture
    def mock_graph(self):
        """Create a mock GraphDB instance"""
        with patch('modules.graphdb.GraphDatabase') as mock_driver:
            graph = GraphDB("bolt://localhost:7687", "neo4j", "password")
            graph.driver.session = MagicMock()
            yield graph

    def test_has_connection_been_attempted_true(self, mock_graph):
        """Test checking if a connection was attempted (returns true)"""
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {'r': 'some_relationship'}
        mock_session.run.return_value = mock_result
        mock_graph.driver.session.return_value.__enter__.return_value = mock_session
        
        result = mock_graph.has_connection_been_attempted(
            "host1", "192.168.1.1", 22, "root", "password", "secret123"
        )
        
        assert result is True
        mock_session.run.assert_called_once()
        args, kwargs = mock_session.run.call_args
        assert "SSH_ATTEMPT" in args[0]
        assert kwargs['from_hostname'] == "host1"
        assert kwargs['ip'] == "192.168.1.1"
        assert kwargs['port'] == 22
        assert kwargs['user'] == "root"
        assert kwargs['method'] == "password"
        assert kwargs['creds'] == "secret123"

    def test_has_connection_been_attempted_false(self, mock_graph):
        """Test checking if a connection was attempted (returns false)"""
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result
        mock_graph.driver.session.return_value.__enter__.return_value = mock_session
        
        result = mock_graph.has_connection_been_attempted(
            "host1", "192.168.1.1", 22, "root", "password", "secret123"
        )
        
        assert result is False

    def test_record_connection_attempt_success(self, mock_graph):
        """Test recording a successful connection attempt"""
        mock_session = MagicMock()
        mock_graph.driver.session.return_value.__enter__.return_value = mock_session
        
        mock_graph.record_connection_attempt(
            "host1", "host2", "192.168.1.1", 22, "root", "password", "secret123", True
        )
        
        # Should call run twice: once to ensure host exists, once to record attempt
        assert mock_session.run.call_count == 2
        
        # Check the second call (record attempt)
        args, kwargs = mock_session.run.call_args
        assert "SSH_ATTEMPT" in args[0]
        assert kwargs['from_hostname'] == "host1"
        assert kwargs['to_hostname'] == "host2"
        assert kwargs['ip'] == "192.168.1.1"
        assert kwargs['port'] == 22
        assert kwargs['user'] == "root"
        assert kwargs['method'] == "password"
        assert kwargs['creds'] == "secret123"
        assert kwargs['success'] is True

    def test_record_connection_attempt_failure(self, mock_graph):
        """Test recording a failed connection attempt (hostname unknown, using IP as fallback)"""
        mock_session = MagicMock()
        mock_graph.driver.session.return_value.__enter__.return_value = mock_session
        
        # When hostname is unknown, IP is used as fallback for to_hostname
        mock_graph.record_connection_attempt(
            "host1", None, "192.168.1.1", 22, "admin", "keyfile", "/path/to/key", False
        )
        
        # Should call run twice: once to ensure host exists, once to record attempt
        assert mock_session.run.call_count == 2
        
        # Check the second call
        args, kwargs = mock_session.run.call_args
        assert kwargs['success'] is False
        # When to_hostname is None, IP is used as hostname
        assert kwargs['to_hostname'] == "192.168.1.1"

    def test_get_all_attempted_connections(self, mock_graph):
        """Test retrieving all attempted connections from a host"""
        mock_session = MagicMock()
        mock_result = [
            {
                'to_hostname': 'host2',
                'ip': '192.168.1.1',
                'port': 22,
                'user': 'root',
                'method': 'password',
                'creds': 'secret123',
                'success': True,
                'last_attempt': 1234567890,
            },
            {
                'to_hostname': 'host3',
                'ip': '192.168.1.2',
                'port': 2222,
                'user': 'admin',
                'method': 'keyfile',
                'creds': '/path/to/key',
                'success': False,
                'last_attempt': 1234567891,
            },
        ]
        mock_session.run.return_value = mock_result
        mock_graph.driver.session.return_value.__enter__.return_value = mock_session
        
        result = mock_graph.get_all_attempted_connections("host1")
        
        assert len(result) == 2
        assert result[0]['to_hostname'] == 'host2'
        assert result[0]['success'] is True
        assert result[1]['to_hostname'] == 'host3'
        assert result[1]['success'] is False

    def test_get_all_known_jump_hosts(self, mock_graph):
        """Test retrieving all known jump hosts"""
        mock_session = MagicMock()
        mock_result = [
            {'hostname': 'jump_host1'},
            {'hostname': 'jump_host2'},
        ]
        mock_session.run.return_value = mock_result
        mock_graph.driver.session.return_value.__enter__.return_value = mock_session
        
        result = mock_graph.get_all_known_jump_hosts("start_host")
        
        assert len(result) == 2
        assert 'jump_host1' in result
        assert 'jump_host2' in result
        mock_session.run.assert_called_once()
        args, kwargs = mock_session.run.call_args
        assert "SSH_ACCESS" in args[0]
        assert kwargs['start_hostname'] == "start_host"

    def test_get_targets_accessible_from_host(self, mock_graph):
        """Test retrieving targets accessible from a host"""
        mock_session = MagicMock()
        mock_result = [
            {'ip': '192.168.1.1', 'port': 22},
            {'ip': '192.168.1.2', 'port': 2222},
            {'ip': '192.168.1.1', 'port': 22},  # Duplicate should be removed
        ]
        mock_session.run.return_value = mock_result
        mock_graph.driver.session.return_value.__enter__.return_value = mock_session
        
        result = mock_graph.get_targets_accessible_from_host("host1")
        
        assert len(result) == 2  # Duplicates removed
        assert ('192.168.1.1', 22) in result
        assert ('192.168.1.2', 2222) in result
        mock_session.run.assert_called_once()
        args, kwargs = mock_session.run.call_args
        assert "SSH_ACCESS" in args[0]
        assert "SSH_ATTEMPT" in args[0]
        assert kwargs['from_hostname'] == "host1"
