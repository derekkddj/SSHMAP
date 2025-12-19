import pytest
import asyncssh
import tempfile
import os
from unittest.mock import MagicMock, AsyncMock
from modules.bruteforce import try_single_credential
from modules.credential_store import Credential, CredentialStore
from modules.SSHSession import SSHSession
from modules.SSHSessionManager import SSHSessionManager
from modules.config import CONFIG


@pytest.mark.asyncio
class TestIntegrationBruteforce:
    async def test_valid_password_machine1(self, docker_compose):
        """Test successful password auth on machine1 (direct, root/root)"""
        creds_path = "/tmp/test_machine1.csv"
        if os.path.exists(creds_path):
            os.unlink(creds_path)
        store = CredentialStore(path=creds_path)
        mgr = MagicMock()
        mgr.add_session = AsyncMock()

        cred = Credential("127.0.0.1", "2222", "root", "root", "password")
        result = await try_single_credential("127.0.0.1", 2222, cred, credential_store=store, ssh_session_manager=mgr)

        assert result is not None
        assert result.user == "root"
        assert result.method == "password"
        assert result.creds == "root"

        # Cleanup
        if result and result.ssh_session:
            await result.ssh_session.close()
        if os.path.exists("/tmp/test_machine1.csv"):
            os.unlink("/tmp/test_machine1.csv")

    async def test_invalid_password_machine1(self, docker_compose):
        """Test failed password auth on machine1"""
        creds_path = "/tmp/test_invalid1.csv"
        if os.path.exists(creds_path):
            os.unlink(creds_path)
        store = CredentialStore(path=creds_path)
        mgr = MagicMock()
        mgr.add_session = AsyncMock()

        cred = Credential("127.0.0.1", "2222", "root", "wrongpass", "password")
        result = await try_single_credential("127.0.0.1", 2222, cred, credential_store=store, ssh_session_manager=mgr)

        assert result is None

    async def test_valid_password_machine2(self, docker_compose):
        """Test successful password auth on machine2 (direct)"""
        creds_path = "/tmp/test_machine2.csv"
        if os.path.exists(creds_path):
            os.unlink(creds_path)
        store = CredentialStore(path=creds_path)
        mgr = MagicMock()
        mgr.add_session = AsyncMock()

        cred = Credential("127.0.0.1", "2223", "root", "root", "password")
        result = await try_single_credential("127.0.0.1", 2223, cred, credential_store=store, ssh_session_manager=mgr)

        assert result is not None
        assert result.user == "root"
        assert result.method == "password"
        assert result.creds == "root"

        # Cleanup
        if result and result.ssh_session:
            await result.ssh_session.close()
        if os.path.exists(creds_path):
            os.unlink(creds_path)

    async def test_key_auth_machine6(self, docker_compose, temp_csv_yaml):
        """Test key auth on machine6 (direct)"""
        # Load key from machine5_key
        with open("tests/machine5_key", "r") as f:
            key_content = f.read()

        # Write to temp file for loading
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.key') as tmp_key_file:
            tmp_key_file.write(key_content)
            tmp_key_path = tmp_key_file.name

        key_obj = asyncssh.read_private_key(tmp_key_path)

        store = CredentialStore(path=temp_csv_yaml[0])
        store.key_objects[tmp_key_path] = key_obj  # Mock key preload

        mgr = MagicMock()
        mgr.add_session = AsyncMock(side_effect=lambda *args, **kwargs: args[1])  # Return the ssh session

        cred = Credential("127.0.0.1", "2224", "root", tmp_key_path, "keyfile")
        result = await try_single_credential("127.0.0.1", 2224, cred, credential_store=store, ssh_session_manager=mgr)

        assert result is not None
        assert result.method == "keyfile"

        # Cleanup
        if result and result.ssh_session:
            await result.ssh_session.close()
        os.unlink(tmp_key_path)

    async def test_machine3_via_machine2(self, docker_compose):
        """Test successful password auth on machine3 (via machine2 jumphost)"""
        creds_path = "/tmp/test_creds.csv"
        if os.path.exists(creds_path):
            os.unlink(creds_path)
        store = CredentialStore(path=creds_path)
        mgr = MagicMock()
        mgr.add_session = AsyncMock(side_effect=lambda *args, **kwargs: args[1])  # Return the ssh session

        # First, connect to machine2 as jumphost
        jumper_session = SSHSession(
            "127.0.0.1",
            "root",
            password="root",
            port=2223,
            key_objects=store.key_objects,
        )
        jumper_connected = await jumper_session.connect()
        assert jumper_connected, "Failed to connect to machine2 jumphost"

        cred = Credential("172.19.0.3", "22", "root", "root", "password")
        result = await try_single_credential(
            "172.19.0.3",
            22,
            cred,
            jumper=jumper_session,
            credential_store=store,
            ssh_session_manager=mgr
        )

        assert result is not None
        assert result.user == "root"
        assert result.method == "password"
        assert result.creds == "root"

        # Cleanup
        if result and result.ssh_session:
            await result.ssh_session.close()
        await jumper_session.close()
        if os.path.exists(creds_path):
            os.unlink(creds_path)

    async def test_machine4_via_machine3_machine2(self, docker_compose):
        """Test successful password auth on machine4 (via machine3 jumphost, which is via machine2)"""
        # Increase timeout for nested jumps
        CONFIG["scan_timeout"] = 60
        creds_path = "/tmp/test_creds2.csv"
        if os.path.exists(creds_path):
            os.unlink(creds_path)
        store = CredentialStore(path=creds_path)
        mgr = MagicMock()
        mgr.add_session = AsyncMock(side_effect=lambda *args, **kwargs: args[1])  # Return the ssh session

        # First, connect to machine2 as jumphost
        jumper2_session = SSHSession(
            "127.0.0.1",
            "root",
            password="root",
            port=2223,
            key_objects=store.key_objects,
        )
        jumper2_connected = await jumper2_session.connect()
        assert jumper2_connected, "Failed to connect to machine2 jumphost"

        # Then, connect to machine3 via machine2
        cred3 = Credential("172.19.0.3", "22", "root", "root", "password")
        result3 = await try_single_credential(
            "172.19.0.3",
            22,
            cred3,
            jumper=jumper2_session,
            credential_store=store,
            ssh_session_manager=mgr
        )
        assert result3 is not None, "Failed to connect to machine3 via machine2"
        jumper3_session = result3.ssh_session

        # Now try machine4 via machine3
        cred = Credential("172.19.0.4", "22", "root", "root", "password")
        result = await try_single_credential(
            "172.19.0.4",
            22,
            cred,
            jumper=jumper3_session,
            credential_store=store,
            ssh_session_manager=mgr
        )

        assert result is not None
        assert result.user == "root"
        assert result.method == "password"
        assert result.creds == "root"

        # Cleanup
        if result and result.ssh_session:
            await result.ssh_session.close()
        if result3 and result3.ssh_session:
            await result3.ssh_session.close()
        await jumper2_session.close()
        if os.path.exists("/tmp/test_creds2.csv"):
            os.unlink("/tmp/test_creds2.csv")

    async def test_machine5_key_via_machine2(self, docker_compose):
        """Test keyfile auth on machine5 (via machine2 jumphost)"""
        # Load key from machine5_key
        with open("tests/machine5_key", "r") as f:
            key_content = f.read()

        # Write to temp file for loading
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.key') as tmp_key_file:
            tmp_key_file.write(key_content)
            tmp_key_path = tmp_key_file.name

        key_obj = asyncssh.read_private_key(tmp_key_path)

        creds_path = "/tmp/test_creds3.csv"
        if os.path.exists(creds_path):
            os.unlink(creds_path)
        store = CredentialStore(path=creds_path)
        store.key_objects[tmp_key_path] = key_obj  # Mock key preload

        mgr = MagicMock()
        mgr.add_session = AsyncMock(side_effect=lambda *args, **kwargs: args[1])  # Return the ssh session

        # First, connect to machine2 as jumphost
        jumper_session = SSHSession(
            "127.0.0.1",
            "root",
            password="root",
            port=2223,
            key_objects=store.key_objects,
        )
        jumper_connected = await jumper_session.connect()
        assert jumper_connected, "Failed to connect to machine2 jumphost"

        cred = Credential("172.19.0.5", "22", "root", tmp_key_path, "keyfile")
        result = await try_single_credential(
            "172.19.0.5",
            22,
            cred,
            jumper=jumper_session,
            credential_store=store,
            ssh_session_manager=mgr
        )

        assert result is not None
        assert result.method == "keyfile"

        # Cleanup
        if result and result.ssh_session:
            await result.ssh_session.close()
        await jumper_session.close()
        os.unlink(tmp_key_path)
        if os.path.exists("/tmp/test_creds3.csv"):
            os.unlink("/tmp/test_creds3.csv")
