import pytest
import asyncio
from unittest.mock import MagicMock
from modules.SSHSession import SSHSession
from modules.SSHSessionManager import SSHSessionManager
from modules.credential_store import CredentialStore


@pytest.mark.asyncio
class TestJumpChainValidation:
    async def test_session_manager_detects_broken_jump_chain(self, docker_compose):
        """
        Test that SSHSessionManager properly detects a broken jump chain and creates a new session.
        
        Scenario:
        1. Use SSHSessionManager to cache a session to machine3 via machine2
        2. Close the machine2 session (break the jump chain)
        3. Try to reuse the cached session - should detect it's broken
        4. SSHSessionManager should create a new working session chain
        """
        # Setup mock graph database that returns a path
        mock_graphdb = MagicMock()
        mock_graphdb.find_path.return_value = [
            ("machine2", {"user": "root", "method": "password", "creds": "root", "ip": "172.19.0.2", "port": 22}, "machine3"),
        ]
        
        credential_store = CredentialStore()
        session_manager = SSHSessionManager(mock_graphdb, credential_store)
        
        # Step 1: Create initial sessions manually and cache them
        machine2_session = SSHSession(
            host="127.0.0.1",
            port=2223,
            user="root",
            password="root",
        )
        await machine2_session.connect()
        assert await machine2_session.is_connected()
        
        machine3_session = SSHSession(
            host="172.19.0.3",
            port=22,
            user="root",
            password="root",
            jumper=machine2_session
        )
        await machine3_session.connect()
        assert await machine3_session.is_connected()
        
        # Cache the machine3 session in session manager
        machine3_key = ("machine3", "root", "password", "root")
        session_manager.sessions[machine3_key] = machine3_session
        
        # Verify the session works
        output = await machine3_session.exec_command("hostname")
        assert "machine3" in output
        
        # Step 2: Close the machine2 (jump) connection to break the chain
        await machine2_session.close()
        await asyncio.sleep(1)
        
        # Step 3: Verify the cached session detects the broken chain
        cached_session = session_manager.sessions.get(machine3_key)
        assert cached_session is machine3_session
        is_connected = await cached_session.is_connected()
        assert not is_connected, "Cached session should detect broken jump chain"
        
        # Step 4: Cleanup
        await machine3_session.close()

    async def test_broken_jump_chain_detection(self, docker_compose):
        """
        Test that a broken intermediate jump connection is detected and a new session is created.
        
        Scenario:
        1. Create a session to machine3 (172.19.0.3) using machine2 (172.19.0.2) as jumphost
        2. Close the machine2 session directly to simulate a broken intermediate connection
        3. Try to get a session to machine3 again
        4. Verify that is_connected() detects the broken chain and a new session is created
        """
        # Step 1: Create direct session to machine2 (jumphost)
        machine2_session = SSHSession(
            host="127.0.0.1",
            port=2223,
            user="root",
            password="root",
        )
        await machine2_session.connect()
        assert await machine2_session.is_connected()
        
        # Step 2: Create session to machine3 via machine2 as jumphost
        machine3_session = SSHSession(
            host="172.19.0.3",
            port=22,
            user="root",
            password="root",
            jumper=machine2_session
        )
        await machine3_session.connect()
        assert await machine3_session.is_connected()
        
        # Step 3: Verify the session is working
        output = await machine3_session.exec_command("hostname")
        assert "machine3" in output
        
        # Step 4: Close the machine2 (intermediate jump) connection
        await machine2_session.close()
        
        # Give it a moment to ensure the connection is fully closed
        await asyncio.sleep(1)
        
        # Step 5: Verify that machine2 is no longer connected
        is_machine2_connected = await machine2_session.is_connected()
        assert not is_machine2_connected, "Machine2 should be disconnected"
        
        # Step 6: Verify that machine3 detects the broken jump chain (recursive check)
        is_machine3_connected = await machine3_session.is_connected()
        assert not is_machine3_connected, "Machine3 should detect broken jump chain"
        
        # Step 7: Create a new session chain to verify a fresh connection works
        # Create a new machine2 session
        new_machine2_session = SSHSession(
            host="127.0.0.1",
            port=2223,
            user="root",
            password="root",
        )
        await new_machine2_session.connect()
        assert await new_machine2_session.is_connected()
        
        # Create a new machine3 session with the new jumphost
        new_machine3_session = SSHSession(
            host="172.19.0.3",
            port=22,
            user="root",
            password="root",
            jumper=new_machine2_session
        )
        await new_machine3_session.connect()
        assert await new_machine3_session.is_connected()
        
        # Verify the new session works
        output = await new_machine3_session.exec_command("hostname")
        assert "machine3" in output
        
        # Cleanup
        await new_machine3_session.close()
        await new_machine2_session.close()
        await machine3_session.close()

    async def test_multi_hop_jump_chain_validation(self, docker_compose):
        """
        Test that a broken connection in a multi-hop chain is detected.
        
        Scenario:
        1. Create chain: machine2 -> machine3 -> machine4
        2. Break machine3 (middle of chain)
        3. Verify machine4 detects the broken chain
        """
        # Step 1: Create machine2 session (first jump)
        machine2_session = SSHSession(
            host="127.0.0.1",
            port=2223,
            user="root",
            password="root",
        )
        await machine2_session.connect()
        assert await machine2_session.is_connected()
        
        # Step 2: Create machine3 session via machine2
        machine3_session = SSHSession(
            host="172.19.0.3",
            port=22,
            user="root",
            password="root",
            jumper=machine2_session
        )
        await machine3_session.connect()
        assert await machine3_session.is_connected()
        
        # Step 3: Create machine4 session via machine3
        machine4_session = SSHSession(
            host="172.19.0.4",
            port=22,
            user="root",
            password="root",
            jumper=machine3_session
        )
        await machine4_session.connect()
        assert await machine4_session.is_connected()
        
        # Step 4: Verify the full chain works
        output = await machine4_session.exec_command("hostname")
        assert "machine4" in output
        
        # Step 5: Break the middle connection (machine3)
        await machine3_session.close()
        await asyncio.sleep(1)
        
        # Step 6: Verify machine3 is disconnected
        assert not await machine3_session.is_connected()
        
        # Step 7: Verify machine4 detects the broken chain (recursive check)
        is_machine4_connected = await machine4_session.is_connected()
        assert not is_machine4_connected, "Machine4 should detect broken chain at machine3"
        
        # Cleanup
        await machine4_session.close()
        await machine2_session.close()

    async def test_healthy_jump_chain_validation(self, docker_compose):
        """
        Test that a healthy jump chain passes validation.
        
        Scenario:
        1. Create chain: machine2 -> machine3
        2. Verify both connections work and is_connected() returns True
        """
        # Create machine2 session
        machine2_session = SSHSession(
            host="127.0.0.1",
            port=2223,
            user="root",
            password="root",
        )
        await machine2_session.connect()
        assert await machine2_session.is_connected()
        
        # Create machine3 session via machine2
        machine3_session = SSHSession(
            host="172.19.0.3",
            port=22,
            user="root",
            password="root",
            jumper=machine2_session
        )
        await machine3_session.connect()
        
        # Verify the healthy chain passes validation
        assert await machine3_session.is_connected()
        
        # Execute a command to prove it actually works
        output = await machine3_session.exec_command("echo 'test'")
        assert "test" in output
        
        # Cleanup
        await machine3_session.close()
        await machine2_session.close()
