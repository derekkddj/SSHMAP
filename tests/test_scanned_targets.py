import pytest
from unittest.mock import MagicMock, patch
from modules.graphdb import GraphDB


class TestScannedTargets:
    """Test the scanned targets tracking functionality"""

    @pytest.fixture
    def mock_graph(self):
        """Create a mock GraphDB instance"""
        with patch('modules.graphdb.GraphDatabase') as mock_driver:
            graph = GraphDB("bolt://localhost:7687", "neo4j", "password")
            graph.driver.session = MagicMock()
            yield graph

    def test_add_scanned_target(self, mock_graph):
        """Test adding a scanned target"""
        mock_session = MagicMock()
        mock_graph.driver.session.return_value.__enter__.return_value = mock_session
        
        mock_graph.add_scanned_target("192.168.1.1")
        
        # Verify that the session.run was called with correct query
        mock_session.run.assert_called_once()
        args, kwargs = mock_session.run.call_args
        assert "MERGE (st:ScannedTarget {ip: $ip})" in args[0]
        assert kwargs['ip'] == "192.168.1.1"
        assert 'timestamp' in kwargs

    def test_is_target_scanned_true(self, mock_graph):
        """Test checking if a target was scanned (returns true)"""
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {'last_scanned': 123456789}
        mock_session.run.return_value = mock_result
        mock_graph.driver.session.return_value.__enter__.return_value = mock_session
        
        result = mock_graph.is_target_scanned("192.168.1.1")
        
        assert result is True
        mock_session.run.assert_called_once()
        args, kwargs = mock_session.run.call_args
        assert "MATCH (st:ScannedTarget {ip: $ip})" in args[0]
        assert kwargs['ip'] == "192.168.1.1"

    def test_is_target_scanned_false(self, mock_graph):
        """Test checking if a target was scanned (returns false)"""
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result
        mock_graph.driver.session.return_value.__enter__.return_value = mock_session
        
        result = mock_graph.is_target_scanned("192.168.1.1")
        
        assert result is False

    def test_get_scanned_targets(self, mock_graph):
        """Test getting all scanned targets"""
        mock_session = MagicMock()
        mock_result = [
            {'ip': '192.168.1.1', 'last_scanned': 123456789},
            {'ip': '192.168.1.2', 'last_scanned': 123456790},
        ]
        mock_session.run.return_value = mock_result
        mock_graph.driver.session.return_value.__enter__.return_value = mock_session
        
        result = mock_graph.get_scanned_targets()
        
        assert len(result) == 2
        assert result[0]['ip'] == '192.168.1.1'
        assert result[1]['ip'] == '192.168.1.2'

    def test_clear_scanned_targets(self, mock_graph):
        """Test clearing all scanned targets"""
        mock_session = MagicMock()
        mock_graph.driver.session.return_value.__enter__.return_value = mock_session
        
        mock_graph.clear_scanned_targets()
        
        mock_session.run.assert_called_once()
        args, kwargs = mock_session.run.call_args
        assert "DELETE st" in args[0]

    def test_are_targets_scanned_batch(self, mock_graph):
        """Test batch checking of multiple targets"""
        mock_session = MagicMock()
        mock_result = [
            {'ip': '192.168.1.1'},
            {'ip': '192.168.1.3'},
        ]
        mock_session.run.return_value = mock_result
        mock_graph.driver.session.return_value.__enter__.return_value = mock_session
        
        ips_to_check = ['192.168.1.1', '192.168.1.2', '192.168.1.3', '192.168.1.4']
        result = mock_graph.are_targets_scanned(ips_to_check)
        
        assert result == {'192.168.1.1', '192.168.1.3'}
        mock_session.run.assert_called_once()
        args, kwargs = mock_session.run.call_args
        assert "WHERE st.ip IN $ips" in args[0]
        assert set(kwargs['ips']) == set(ips_to_check)

    def test_are_targets_scanned_empty(self, mock_graph):
        """Test batch checking with empty list"""
        result = mock_graph.are_targets_scanned([])
        assert result == set()
