import pytest
from modules.bruteforce import try_single_credential
from modules.credential_store import Credential
from modules.SSHSession import SSHSession


@pytest.mark.asyncio
async def test_invalid_password_auth():
    cred = Credential(
        remote_ip="172.19.0.2",
        port=22,
        user="root",
        secret="wrongpassword",
        method="password",
    )
    result = await try_single_credential("172.19.0.2", 22, cred)
    assert result is None


@pytest.mark.asyncio
async def test_ssh_connection_fail():
    ssh = SSHSession("invalid.host", "user", password="pass")
    success = await ssh.connect()
    assert success is False
