import asyncio
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncssh
import pytest

from modules.attempt_store import AttemptStore
from modules.SSHSession import SSHSession
from modules.bruteforce import Result, try_all, try_single_credential
from modules.credential_store import Credential


@pytest.fixture
def store(tmp_path):
    result = AttemptStore(str(tmp_path / "attempts.db"))
    yield result
    result.close()


def rows(store):
    with sqlite3.connect(store.db_path) as conn:
        return conn.execute("SELECT success, status, timestamp, target_hostname FROM ssh_attempts ORDER BY id").fetchall()


async def record(store, status=None, hostname="target"):
    await store.record_attempt("source", hostname, "127.0.0.1", 22, "user", "password", "secret",
                               status == "success", status=status)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["success", "auth_failed", "connection_failed", "timeout", "session_failed", "unknown", None])
async def test_fresh_schema_and_filtering(store, status):
    await record(store, status)
    assert rows(store)[0][:2] == (int(status == "success"), status or "unknown")
    expected = {("user", "password", "secret")} if status in ("success", "auth_failed") else set()
    assert store.get_attempted_credentials("source", "127.0.0.1", 22) == expected


@pytest.mark.asyncio
async def test_latest_status_timestamp_and_ever_success(store):
    for status in ("unknown", "connection_failed", "auth_failed", "success", "timeout", "success"):
        with sqlite3.connect(store.db_path) as conn:
            conn.execute("UPDATE ssh_attempts SET timestamp = '2000-01-01'")
        await record(store, status, "real-host" if status == "success" else "target")
        current = rows(store)
        assert len(current) == 1
        assert current[0][1] == status
        assert current[0][2] != "2000-01-01"
        if status == "timeout":
            assert current[0][0] == 1
            assert current[0][3] == "real-host"
            assert store.get_attempted_credentials("source", "127.0.0.1", 22) == set()
            assert store.get_successful_attempts("source", "127.0.0.1", 22) == {("user", "password", "secret")}


@pytest.mark.asyncio
@pytest.mark.parametrize("duplicates", [False, True])
async def test_legacy_migration_preserves_rows_and_duplicate_fallback(tmp_path, duplicates):
    path = str(tmp_path / "legacy.db")
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE ssh_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, source_hostname TEXT NOT NULL,
            target_hostname TEXT NOT NULL, target_ip TEXT NOT NULL, target_port INTEGER NOT NULL,
            username TEXT NOT NULL, method TEXT NOT NULL, credential TEXT NOT NULL,
            success BOOLEAN NOT NULL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("INSERT INTO ssh_attempts VALUES (1, 'source', 'target', '127.0.0.1', 22, 'user', 'password', 'secret', 0, '2000-01-01')")
        conn.execute("INSERT INTO ssh_attempts VALUES (2, 'source', 'known', '127.0.0.1', 22, 'other', 'keyfile', 'key', 1, '2001-01-01')")
        if duplicates:
            conn.execute("INSERT INTO ssh_attempts SELECT 3, source_hostname, target_hostname, target_ip, target_port, username, method, credential, success, timestamp FROM ssh_attempts WHERE id = 1")
    store = AttemptStore(path)
    try:
        assert rows(store)[:2] == [(0, "unknown", "2000-01-01", "target"), (1, "success", "2001-01-01", "known")]
        assert store.get_attempted_credentials("source", "127.0.0.1", 22) == {("other", "keyfile", "key")}
        # Independent stores must also serialize the legacy no-unique-index path.
        second = AttemptStore(path)
        try:
            await asyncio.gather(*(record(store if i % 2 else second, "connection_failed") for i in range(12)))
        finally:
            second.close()
        for status in ("connection_failed", "success", "timeout"):
            await record(store, status)
        current = rows(store)
        assert len(current) == (3 if duplicates else 2)
        matching = [current[0]] + ([current[2]] if duplicates else [])
        assert all(row[0:2] == (1, "timeout") and row[2] != "2000-01-01" for row in matching)
        with sqlite3.connect(path) as conn:
            indexes = {row[1] for row in conn.execute("PRAGMA index_list(ssh_attempts)")}
        assert ("idx_attempt_unique" in indexes) is not duplicates
    finally:
        store.close()
    reopened = AttemptStore(path)
    try:
        assert rows(reopened) == current  # Migration is idempotent.
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_invalid_status_is_not_silently_written(store):
    with pytest.raises(ValueError):
        await record(store, "typo")
    with pytest.raises(ValueError):
        await store.record_attempt("s", "t", "ip", 22, "u", "password", "p", True, "auth_failed")
    assert rows(store) == []


@pytest.fixture
def ssh_env(monkeypatch):
    connection = SimpleNamespace(
        run=AsyncMock(return_value=SimpleNamespace(exit_status=0, stdout="target\n", stderr="")),
        close=lambda: None, wait_closed=AsyncMock(),
    )
    connect = AsyncMock(return_value=connection)
    monkeypatch.setattr("modules.SSHSession.asyncssh.connect", connect)
    # Speed up retries/stabilization without replacing wait_for.
    monkeypatch.setattr("modules.SSHSession.asyncio.sleep", AsyncMock())
    monkeypatch.setattr("modules.SSHSession.CONFIG", {"scan_timeout": 1})
    monkeypatch.setattr("modules.bruteforce.CONFIG", {"scan_timeout": 1, "record_connection_attempts": True})
    cred = Credential("127.0.0.1", "22", "user", "secret", "password")
    creds = SimpleNamespace(key_objects={}, store=AsyncMock(), get_credentials_host_and_bruteforce=lambda *_: [cred])
    manager = SimpleNamespace(add_session=AsyncMock(side_effect=lambda _, ssh, *args: ssh))
    return connect, connection, cred, creds, manager


@pytest.mark.asyncio
@pytest.mark.parametrize("error,status", [
    (asyncssh.PermissionDenied("account policy or auth rejection"), "auth_failed"),
    (asyncssh.ConnectionLost("overload"), "connection_failed"),
    (asyncssh.ChannelOpenError(1, "forwarding prohibited"), "connection_failed"),
    (asyncssh.KeyExchangeFailed("no matching algorithms"), "connection_failed"),
    (ConnectionRefusedError("refused"), "connection_failed"),
    (asyncio.TimeoutError(), "timeout"),
    (ValueError("invalid config"), "unknown"),
    (FileNotFoundError("local key"), "unknown"),
])
async def test_errors_propagate_through_bruteforce_to_sqlite(store, ssh_env, error, status):
    connect, _, _, creds, manager = ssh_env
    connect.side_effect = error
    assert await try_all("127.0.0.1", 22, credential_store=creds, ssh_session_manager=manager,
                         attempt_store=store, source_hostname="source", max_retries=2) == []
    assert rows(store)[0][:2] == (0, status)
    assert connect.await_count == (2 if isinstance(error, asyncssh.ConnectionLost) else 1)
    before = connect.await_count
    await try_all("127.0.0.1", 22, credential_store=creds, ssh_session_manager=manager,
                  attempt_store=store, source_hostname="source", max_retries=1)
    assert connect.await_count == before + (0 if status == "auth_failed" else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["password", "keyfile"])
async def test_outer_wait_for_timeout(store, ssh_env, monkeypatch, method):
    connect, _, cred, creds, manager = ssh_env
    cred = Credential("127.0.0.1", "22", "user", "secret", method)
    creds.get_credentials_host_and_bruteforce = lambda *_: [cred]
    creds.key_objects = {"secret": object()}
    async def stalled(*args, **kwargs):
        await asyncio.Event().wait()
    connect.side_effect = stalled
    monkeypatch.setattr("modules.bruteforce.CONFIG", {"scan_timeout": 0.01, "record_connection_attempts": True})
    await try_all("127.0.0.1", 22, credential_store=creds, ssh_session_manager=manager,
                  attempt_store=store, source_hostname="source")
    assert rows(store)[0][:2] == (0, "timeout")


@pytest.mark.asyncio
@pytest.mark.parametrize("probe_error", [asyncssh.PermissionDenied("command policy"), asyncssh.ConnectionLost("post-login"), None])
async def test_post_auth_probe_failure(store, ssh_env, probe_error):
    _, connection, _, creds, manager = ssh_env
    connection.run.side_effect = probe_error
    if probe_error is None:
        connection.run.return_value = SimpleNamespace(exit_status=1, stdout="", stderr="hostname unavailable")
    await try_all("127.0.0.1", 22, credential_store=creds, ssh_session_manager=manager,
                  attempt_store=store, source_hostname="source", max_retries=1)
    assert rows(store)[0][:2] == (0, "session_failed")
    creds.store.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_local_key_never_attempts_auth(store, ssh_env):
    connect, _, cred, creds, manager = ssh_env
    cred = Credential("127.0.0.1", "22", "user", "secret", "keyfile")
    creds.get_credentials_host_and_bruteforce = lambda *_: [cred]
    await try_all("127.0.0.1", 22, credential_store=creds, ssh_session_manager=manager,
                  attempt_store=store, source_hostname="source")
    connect.assert_not_awaited()
    assert rows(store)[0][1] == "unknown"


@pytest.mark.asyncio
async def test_success_existing_result_bool_and_exception_apis(store, ssh_env):
    connect, _, cred, creds, manager = ssh_env
    outcome = {}
    result = await try_single_credential("127.0.0.1", 22, cred, credential_store=creds,
                                         ssh_session_manager=manager, _outcome=outcome)
    assert isinstance(result, Result)
    assert outcome == {"status": "success"}
    await try_all("127.0.0.1", 22, credential_store=creds, ssh_session_manager=manager,
                  attempt_store=store, source_hostname="source")
    assert rows(store)[0][:2] == (1, "success")
    session = SSHSession("127.0.0.1", "user", password="secret")
    assert await session.connect() is True
    connect.side_effect = asyncssh.PermissionDenied("rejected")
    assert await session.connect() is False
    assert session.attempt_status == "auth_failed"
    assert await try_single_credential("127.0.0.1", 22, cred, credential_store=creds, ssh_session_manager=manager) is None
    connect.side_effect = asyncssh.ConnectionLost("retry")
    with pytest.raises(asyncssh.ConnectionLost):
        await try_single_credential("127.0.0.1", 22, cred, credential_store=creds, ssh_session_manager=manager)


@pytest.mark.asyncio
async def test_connection_lost_retry_then_success(store, ssh_env):
    connect, connection, _, creds, manager = ssh_env
    connect.side_effect = [asyncssh.ConnectionLost("transient"), connection]
    results = await try_all("127.0.0.1", 22, credential_store=creds, ssh_session_manager=manager,
                            attempt_store=store, source_hostname="source", max_retries=2)
    assert len(results) == 1
    assert connect.await_count == 2
    assert rows(store)[0][:2] == (1, "success")
    assert len(rows(store)) == 1


@pytest.mark.asyncio
async def test_outer_deadline_during_post_auth_is_timeout(store, ssh_env, monkeypatch):
    _, connection, _, creds, manager = ssh_env
    async def stalled(*args, **kwargs):
        await asyncio.Event().wait()
    connection.run.side_effect = stalled
    monkeypatch.setattr("modules.bruteforce.CONFIG", {"scan_timeout": 0.01, "record_connection_attempts": True})
    await try_all("127.0.0.1", 22, credential_store=creds, ssh_session_manager=manager,
                  attempt_store=store, source_hostname="source")
    assert rows(store)[0][:2] == (0, "timeout")
    connection.wait_closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_fallback_also_records_latest_outcome(store, ssh_env):
    _, _, _, creds, manager = ssh_env
    await record(store, "auth_failed")
    graph = SimpleNamespace(get_connections_from_host=lambda _: [{
        "to": "target", "props": {"ip": "127.0.0.1", "port": 22, "user": "user",
                                    "method": "password", "creds": "secret"},
    }])
    results = await try_all("127.0.0.1", 22, credential_store=creds, ssh_session_manager=manager,
                            attempt_store=store, source_hostname="source", graphdb=graph)
    assert len(results) == 1
    assert rows(store)[0][:2] == (1, "success")


@pytest.mark.asyncio
async def test_closed_port_marker_retryable(tmp_path, store, ssh_env, monkeypatch):
    import importlib.util
    from pathlib import Path
    from modules.config import CONFIG

    # Scanner constructs its global store at import: isolate it from user output.
    monkeypatch.setitem(CONFIG.as_dict(), "attempt_db_path", str(tmp_path / "scanner.db"))
    spec = importlib.util.spec_from_file_location("status_test_scanner", Path(__file__).resolve().parents[1] / "SSHMAP.py")
    scanner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scanner)
    imported_store = scanner.attempt_store
    monkeypatch.setattr(scanner, "attempt_store", store)
    monkeypatch.setattr(scanner, "ssh_ports", [22])
    monkeypatch.setattr(scanner, "check_open_port", AsyncMock(return_value=False))
    _, _, _, creds, _ = ssh_env
    try:
        for _ in range(2):
            await scanner.handle_target("127.0.0.1", 1, creds, 1, scan_origin_host="source", record_closed_port_attempts=True)
        assert scanner.check_open_port.await_count == 2
        assert len(rows(store)) == 1
        assert rows(store)[0][:2] == (0, "connection_failed")
        assert store.get_attempted_credentials("source", "127.0.0.1", 22) == set()
    finally:
        imported_store.close()
