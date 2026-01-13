import pytest
import tempfile
import os
from modules.attempt_store import AttemptStore


class TestConnectionAttempts:
    """Test the connection attempt tracking functionality"""

    @pytest.fixture
    def attempt_store(self):
        """Create an AttemptStore instance with a temporary database"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        store = AttemptStore(db_path=db_path)
        yield store
        
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_record_connection_attempt(self, attempt_store):
        """Test recording a connection attempt to SQLite"""
        await attempt_store.record_attempt(
            source_hostname="host1",
            target_hostname="host2",
            target_ip="192.168.1.1",
            target_port=22,
            username="root",
            method="password",
            credential="secret123",
            success=True,
        )
        
        # Verify attempt was recorded
        attempts = attempt_store.get_attempted_credentials("host1", "192.168.1.1", 22)
        assert len(attempts) == 1
        assert ("root", "password", "secret123") in attempts

    @pytest.mark.asyncio
    async def test_record_multiple_attempts(self, attempt_store):
        """Test recording multiple connection attempts"""
        credentials = [
            ("root", "password", "secret123"),
            ("admin", "password", "admin123"),
            ("ubuntu", "keyfile", "/path/to/key"),
        ]
        
        for user, method, cred in credentials:
            await attempt_store.record_attempt(
                source_hostname="host1",
                target_hostname="host2",
                target_ip="192.168.1.1",
                target_port=22,
                username=user,
                method=method,
                credential=cred,
                success=False,
            )
        
        # Verify all attempts were recorded
        attempts = attempt_store.get_attempted_credentials("host1", "192.168.1.1", 22)
        assert len(attempts) == 3
        for user, method, cred in credentials:
            assert (user, method, cred) in attempts

    @pytest.mark.asyncio
    async def test_get_attempted_credentials_empty(self, attempt_store):
        """Test getting attempted credentials when none exist"""
        attempts = attempt_store.get_attempted_credentials("host1", "192.168.1.1", 22)
        assert len(attempts) == 0
        assert isinstance(attempts, set)

    @pytest.mark.asyncio
    async def test_get_successful_attempts(self, attempt_store):
        """Test retrieving only successful attempts"""
        # Record mixed attempts
        await attempt_store.record_attempt(
            source_hostname="host1",
            target_hostname="host2",
            target_ip="192.168.1.1",
            target_port=22,
            username="root",
            method="password",
            credential="secret123",
            success=True,  # Success
        )
        
        await attempt_store.record_attempt(
            source_hostname="host1",
            target_hostname="host2",
            target_ip="192.168.1.1",
            target_port=22,
            username="admin",
            method="password",
            credential="admin123",
            success=False,  # Failed
        )
        
        # Get only successful attempts
        successful = attempt_store.get_successful_attempts("host1", "192.168.1.1", 22)
        
        assert len(successful) == 1
        assert ("root", "password", "secret123") in successful
        assert ("admin", "password", "admin123") not in successful

    @pytest.mark.asyncio
    async def test_credential_deduplication(self, attempt_store):
        """Test that duplicate attempts return same credential set"""
        # Record the same credential twice (simulating a retry)
        await attempt_store.record_attempt(
            source_hostname="host1",
            target_hostname="host2",
            target_ip="192.168.1.1",
            target_port=22,
            username="root",
            method="password",
            credential="secret123",
            success=True,
        )
        
        await attempt_store.record_attempt(
            source_hostname="host1",
            target_hostname="host2",
            target_ip="192.168.1.1",
            target_port=22,
            username="root",
            method="password",
            credential="secret123",
            success=True,
        )
        
        # Should only return one unique (user, method, credential) tuple
        attempts = attempt_store.get_attempted_credentials("host1", "192.168.1.1", 22)
        assert len(attempts) == 1
        assert ("root", "password", "secret123") in attempts

    @pytest.mark.asyncio
    async def test_different_targets_isolated(self, attempt_store):
        """Test that attempts on different targets are isolated"""
        # Record attempts on different targets
        await attempt_store.record_attempt(
            source_hostname="host1",
            target_hostname="host2",
            target_ip="192.168.1.1",
            target_port=22,
            username="root",
            method="password",
            credential="secret123",
            success=True,
        )
        
        await attempt_store.record_attempt(
            source_hostname="host1",
            target_hostname="host3",
            target_ip="192.168.1.2",
            target_port=22,
            username="root",
            method="password",
            credential="secret456",
            success=False,
        )
        
        # Get attempts for first target
        attempts_1 = attempt_store.get_attempted_credentials("host1", "192.168.1.1", 22)
        assert len(attempts_1) == 1
        assert ("root", "password", "secret123") in attempts_1
        
        # Get attempts for second target
        attempts_2 = attempt_store.get_attempted_credentials("host1", "192.168.1.2", 22)
        assert len(attempts_2) == 1
        assert ("root", "password", "secret456") in attempts_2
