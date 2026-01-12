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
    
    def test_has_connection_been_attempted_checks_queue(self, mock_graph):
        """Test that has_connection_been_attempted checks the in-memory queue"""
        # Add an attempt to the queue
        mock_graph._attempt_queue.append({
            'from_hostname': 'host1',
            'to_hostname': 'host2',
            'to_ip': '192.168.1.1',
            'port': 22,
            'user': 'root',
            'method': 'password',
            'creds': 'secret123',
            'success': True,
            'time': 1234567890
        })
        
        # Should find it in the queue without querying the database
        result = mock_graph.has_connection_been_attempted(
            "host1", "192.168.1.1", 22, "root", "password", "secret123"
        )
        
        assert result is True

    @pytest.mark.asyncio
    async def test_record_connection_attempt_queues(self, mock_graph):
        """Test that recording a connection attempt adds it to the queue"""
        await mock_graph.record_connection_attempt(
            "host1", "host2", "192.168.1.1", 22, "root", "password", "secret123", True
        )
        
        # Should have added to the queue
        assert len(mock_graph._attempt_queue) == 1
        attempt = mock_graph._attempt_queue[0]
        assert attempt['from_hostname'] == "host1"
        assert attempt['to_hostname'] == "host2"
        assert attempt['to_ip'] == "192.168.1.1"
        assert attempt['port'] == 22
        assert attempt['user'] == "root"
        assert attempt['method'] == "password"
        assert attempt['creds'] == "secret123"
        assert attempt['success'] is True

    @pytest.mark.asyncio
    async def test_record_connection_attempt_batching(self, mock_graph):
        """Test that connection attempts are batched and flushed at batch_size"""
        mock_session = MagicMock()
        mock_graph.driver.session.return_value.__enter__.return_value = mock_session
        mock_graph._batch_size = 3  # Set a small batch size for testing
        
        # Add attempts one by one
        for i in range(2):
            await mock_graph.record_connection_attempt(
                "host1", "host2", f"192.168.1.{i}", 22, "root", "password", f"secret{i}", True
            )
        
        # Should not have flushed yet
        assert mock_session.run.call_count == 0
        assert len(mock_graph._attempt_queue) == 2
        
        # Add one more to trigger the batch flush
        await mock_graph.record_connection_attempt(
            "host1", "host2", "192.168.1.3", 22, "root", "password", "secret3", True
        )
        
        # Should have flushed now
        assert mock_session.run.call_count == 2  # Once for hosts, once for attempts
        assert len(mock_graph._attempt_queue) == 0

    @pytest.mark.asyncio
    async def test_flush_attempts(self, mock_graph):
        """Test manual flushing of queued attempts"""
        mock_session = MagicMock()
        mock_graph.driver.session.return_value.__enter__.return_value = mock_session
        
        # Add some attempts to the queue manually
        for i in range(5):
            mock_graph._attempt_queue.append({
                'from_hostname': 'host1',
                'to_hostname': 'host2',
                'to_ip': f'192.168.1.{i}',
                'port': 22,
                'user': 'root',
                'method': 'password',
                'creds': f'secret{i}',
                'success': True,
                'time': 1234567890 + i
            })
        
        # Flush manually
        await mock_graph.flush_attempts()
        
        # Should have cleared the queue and written to DB
        assert len(mock_graph._attempt_queue) == 0
        assert mock_session.run.call_count == 2  # Once for hosts, once for attempts

    def test_close_flushes_remaining_attempts(self, mock_graph):
        """Test that closing the graph flushes any remaining attempts"""
        mock_session = MagicMock()
        mock_graph.driver.session.return_value.__enter__.return_value = mock_session
        
        # Add some attempts to the queue
        for i in range(3):
            mock_graph._attempt_queue.append({
                'from_hostname': 'host1',
                'to_hostname': 'host2',
                'to_ip': f'192.168.1.{i}',
                'port': 22,
                'user': 'root',
                'method': 'password',
                'creds': f'secret{i}',
                'success': True,
                'time': 1234567890 + i
            })
        
        # Close should flush
        mock_graph.close()
        
        # Should have flushed and closed
        assert len(mock_graph._attempt_queue) == 0
        assert mock_session.run.call_count == 2  # Once for hosts, once for attempts

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
