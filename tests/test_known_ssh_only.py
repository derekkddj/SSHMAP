import importlib.util
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.attempt_store import AttemptStore
from modules.credential_store import Credential


spec = importlib.util.spec_from_file_location(
    "sshmap_known_ssh", Path(__file__).resolve().parents[1] / "SSHMAP.py"
)
SSHMAP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SSHMAP)


@pytest.fixture
def store(tmp_path):
    result = AttemptStore(str(tmp_path / "attempts.db"))
    yield result
    result.close()


async def record(store, status, source="local", ip="10.0.0.1", port=22, user="old"):
    await store.record_attempt(source, "target", ip, port, user, "password", "secret",
                               status == "success", status=status)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["success", "auth_failed", "session_failed", "connection_failed", "timeout", "unknown"])
async def test_evidence_survives_latest_failure_and_reopen(store, status):
    assert not store.is_known_ssh_target("local", "10.0.0.1", 22)
    await record(store, status)
    expected = status in ("success", "auth_failed", "session_failed")
    assert store.is_known_ssh_target("local", "10.0.0.1", 22) is expected
    for failure in ("timeout", "connection_failed", "unknown"):
        await record(store, failure)
        assert store.is_known_ssh_target("local", "10.0.0.1", 22) is expected
        # Reachability does not change latest-status credential filtering.
        assert store.get_attempted_credentials("local", "10.0.0.1", 22) == set()
    reopened = AttemptStore(store.db_path)
    try:
        assert reopened.is_known_ssh_target("local", "10.0.0.1", 22) is expected
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_origin_ip_port_scope_and_partial_index(store):
    await record(store, "auth_failed", source="jump", port=2222)
    await record(store, "connection_failed")
    assert store.is_known_ssh_target("jump", "10.0.0.1", 2222)
    for source, ip, port in [("local", "10.0.0.1", 2222), ("jump", "10.0.0.1", 22),
                             ("jump", "10.0.0.2", 2222), (None, "10.0.0.1", 2222)]:
        assert not store.is_known_ssh_target(source, ip, port)
    with sqlite3.connect(store.db_path) as conn:
        plan = conn.execute("""EXPLAIN QUERY PLAN SELECT 1 FROM ssh_attempts
            WHERE source_hostname = ? AND target_ip = ? AND target_port = ?
            AND ssh_reachable = 1 LIMIT 1""", ("jump", "10.0.0.1", 2222)).fetchall()
        assert "idx_known_ssh_lookup" in str(plan)


@pytest.mark.parametrize("with_status", [False, True])
@pytest.mark.asyncio
async def test_additive_migration_backfills_available_evidence(tmp_path, with_status):
    path = str(tmp_path / "legacy.db")
    statuses = ["auth_failed", "session_failed", "timeout", "connection_failed", "unknown", "success"]
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE ssh_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, source_hostname TEXT NOT NULL,
            target_hostname TEXT NOT NULL, target_ip TEXT NOT NULL, target_port INTEGER NOT NULL,
            username TEXT NOT NULL, method TEXT NOT NULL, credential TEXT NOT NULL,
            success BOOLEAN NOT NULL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        if with_status:
            conn.execute("ALTER TABLE ssh_attempts ADD COLUMN status TEXT NOT NULL DEFAULT 'unknown'")
        for i, status in enumerate(statuses):
            # Include ever-success=1 with latest timeout, plus legacy duplicates.
            success = int(status in ("success", "timeout"))
            conn.execute("""INSERT INTO ssh_attempts
                (source_hostname, target_hostname, target_ip, target_port, username, method, credential, success, timestamp)
                VALUES ('local', 'target', ?, 22, 'old', 'password', 'secret', ?, '2000-01-01')""",
                         (f"10.0.0.{i}", success))
            if with_status:
                conn.execute("UPDATE ssh_attempts SET status = ? WHERE target_ip = ?", (status, f"10.0.0.{i}"))
        conn.execute("""INSERT INTO ssh_attempts (source_hostname, target_hostname, target_ip, target_port,
            username, method, credential, success, timestamp)
            SELECT source_hostname, target_hostname, target_ip, target_port, username, method,
            credential, success, timestamp FROM ssh_attempts WHERE id = 1""")
    store = AttemptStore(path)
    try:
        for i, status in enumerate(statuses):
            expected = status in (("auth_failed", "session_failed", "timeout", "success") if with_status else ("timeout", "success"))
            assert store.is_known_ssh_target("local", f"10.0.0.{i}", 22) is expected
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT count(*) FROM ssh_attempts WHERE timestamp = '2000-01-01'").fetchone()[0] == 7
        await record(store, "auth_failed", ip="10.0.0.0")
        await record(store, "timeout", ip="10.0.0.0")
    finally:
        store.close()
    reopened = AttemptStore(path)
    try:
        assert reopened.is_known_ssh_target("local", "10.0.0.0", 22)
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT count(*) FROM ssh_attempts").fetchone()[0] == 7
    finally:
        reopened.close()


def test_read_error_fails_closed(store, monkeypatch):
    warning = MagicMock()
    monkeypatch.setattr("modules.attempt_store.sshmap_logger.warning", warning)
    monkeypatch.setattr("modules.attempt_store.sqlite3.connect", MagicMock(side_effect=sqlite3.OperationalError("unavailable")))
    assert not store.is_known_ssh_target("local", "10.0.0.1", 22)
    assert "Excluding target" in warning.call_args.args[0]


@pytest.fixture
def scanner(monkeypatch, store):
    monkeypatch.setattr(SSHMAP, "attempt_store", store)
    monkeypatch.setattr(SSHMAP, "start_host", "local")
    monkeypatch.setattr(SSHMAP, "ssh_ports", [22, 2222])
    monkeypatch.setattr(SSHMAP, "max_depth", 3)
    monkeypatch.setattr(SSHMAP, "graph", None)
    monkeypatch.setattr(SSHMAP, "CONFIG", {"record_connection_attempts": True})
    port_check = AsyncMock(return_value=True)
    try_all = AsyncMock(return_value=[])
    monkeypatch.setattr(SSHMAP, "check_open_port", port_check)
    monkeypatch.setattr(SSHMAP.bruteforce, "try_all", try_all)
    creds = MagicMock()
    creds.get_credentials_host_and_bruteforce.return_value = [Credential("_bruteforce", 22, "new", "new-secret", "password")]
    return port_check, try_all, creds


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["direct", "proxy", "recursive", "start-from"])
@pytest.mark.parametrize("force", [False, True])
async def test_scope_precedes_port_and_credentials(scanner, store, path, force):
    port_check, try_all, creds = scanner
    jump = MagicMock() if path in ("recursive", "start-from") else None
    if jump:
        jump.get_remote_hostname.return_value = "jump"
    origin = "jump" if jump else "local"
    await record(store, "auth_failed", source=origin)
    # Wrong origin and port evidence must not admit other tuples.
    await record(store, "success", source="elsewhere", port=2222)
    kwargs = dict(jump=jump, current_depth=2 if path == "recursive" else 1,
                  proxy_url="socks5://127.0.0.1:9050" if path == "proxy" else None,
                  force_rescan=force, known_ssh_only=True, scan_origin_host="local")
    await SSHMAP.handle_target("10.0.0.1", 1, creds, **kwargs)
    try_all.assert_awaited_once()
    assert try_all.call_args.args[1] == 22
    assert try_all.call_args.kwargs["source_hostname"] == origin
    assert try_all.call_args.kwargs["force_rescan"] is force
    # Existing start-from depth-1 port-check behavior is unchanged.
    assert port_check.await_count == int(path in ("direct", "start-from"))
    port_check.reset_mock()
    try_all.reset_mock()
    creds.reset_mock()
    await SSHMAP.handle_target("10.0.0.99", 1, creds, **kwargs)
    port_check.assert_not_awaited()
    try_all.assert_not_awaited()
    creds.get_credentials_host_and_bruteforce.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_session", [False, True])
async def test_unknown_jump_does_not_use_local_evidence(scanner, store, missing_session):
    port_check, try_all, creds = scanner
    await record(store, "success")
    jump = None if missing_session else MagicMock()
    if jump is not None:
        jump.get_remote_hostname.return_value = None
    await SSHMAP.handle_target("10.0.0.1", 1, creds, 2, jump=jump, known_ssh_only=True)
    port_check.assert_not_awaited()
    try_all.assert_not_awaited()


@pytest.mark.asyncio
async def test_default_off_scans_unknown_targets(scanner):
    _, try_all, creds = scanner
    await SSHMAP.handle_target("10.0.0.99", 1, creds, 1)
    assert try_all.await_count == 2


@pytest.mark.parametrize("enabled", [False, True])
def test_cli_flag_default_and_combinations(monkeypatch, enabled):
    argv = ["sshmap", "--targets", "10.0.0.1", "--no-recursion", "--no-import-creds", "--force-rescan"]
    if enabled:
        argv.append("--known-ssh-only")
    monkeypatch.setattr(SSHMAP.sys, "argv", argv)
    monkeypatch.setattr(SSHMAP, "CONFIG", {"record_connection_attempts": True})
    async_main = MagicMock(return_value="scan")
    monkeypatch.setattr(SSHMAP, "async_main", async_main)
    monkeypatch.setattr(SSHMAP.asyncio, "run", MagicMock())
    SSHMAP.main()
    args = async_main.call_args.args[0]
    assert args.known_ssh_only is enabled
    assert args.no_import_creds and args.force_rescan


def test_cli_rejects_disabled_tracking_before_graph(monkeypatch, capsys):
    monkeypatch.setattr(SSHMAP.sys, "argv", ["sshmap", "--targets", "10.0.0.1", "--known-ssh-only"])
    monkeypatch.setattr(SSHMAP, "CONFIG", {"record_connection_attempts": False})
    graph_class = MagicMock()
    monkeypatch.setattr(SSHMAP.graphdb, "GraphDB", graph_class)
    with pytest.raises(SystemExit) as exc:
        SSHMAP.main()
    assert exc.value.code == 2
    assert "requires record_connection_attempts: true" in capsys.readouterr().err
    graph_class.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("start_from", [None, "remote-start"])
async def test_main_propagates_scope_to_recursive_jobs_with_csv_only(scanner, store, monkeypatch, start_from):
    from contextlib import nullcontext

    _, try_all, creds = scanner
    origin = start_from or "local"
    await record(store, "success", source=origin)
    await record(store, "auth_failed", source="jump", ip="10.0.0.2")
    graph = MagicMock()
    monkeypatch.setattr(SSHMAP, "graph", graph)
    monkeypatch.setattr(SSHMAP, "visited_attempts", set())
    monkeypatch.setattr(SSHMAP, "CredentialStore", MagicMock(return_value=creds))
    monkeypatch.setattr(SSHMAP, "read_targets", MagicMock(return_value=["10.0.0.1", "10.0.0.2", "10.0.0.99"]))
    imported = MagicMock(side_effect=AssertionError("must not import credentials"))
    monkeypatch.setattr(SSHMAP, "read_list_from_file_or_string", imported)
    monkeypatch.setattr(SSHMAP, "load_keys", imported)
    monkeypatch.setattr(SSHMAP, "Live", lambda *a, **kw: nullcontext())
    monkeypatch.setattr(SSHMAP, "start_pause_key_listener", lambda *a: None)
    monkeypatch.setattr(SSHMAP, "notifier", MagicMock())
    monkeypatch.setattr(SSHMAP, "get_remote_ip", AsyncMock(return_value=[{"ip": "10.0.0.1", "mask": 32}]))
    jump = MagicMock()
    jump.get_remote_hostname.return_value = "jump"
    initial_jump = MagicMock()
    initial_jump.get_remote_hostname.return_value = origin
    initial_jump.is_connected = AsyncMock(return_value=True)
    manager = MagicMock()
    manager.get_session = AsyncMock(side_effect=lambda host, source: initial_jump if host == start_from else jump)
    manager.close_all = AsyncMock()
    monkeypatch.setattr(SSHMAP, "SSHSessionManager", MagicMock(return_value=manager))
    first_result = SimpleNamespace(ssh_session=True, user="new", method="password", creds="secret",
                                   get_ssh_connection=lambda: jump)
    try_all.side_effect = [[first_result], []]
    args = SimpleNamespace(
        credentialspath="unused.csv", targets="targets", no_import_creds=True,
        force_targets="targets", blacklist=None, whitelist=None, extra_recursive_targets=None,
        force_rescan=False, known_ssh_only=True, no_recursion=False, proxy=None,
        start_from=start_from, ordered_targets=True, maxworkers=1, maxworkers_ssh=1,
        max_retries=1, record_closed_port_attempts=False,
    )
    await SSHMAP.async_main(args)
    assert [(call.args[0], call.kwargs["source_hostname"]) for call in try_all.await_args_list] == [
        ("10.0.0.1", origin), ("10.0.0.2", "jump")
    ]
    imported.assert_not_called()
    assert "jump" in SSHMAP.visited_attempts


@pytest.mark.asyncio
@pytest.mark.parametrize("force", [False, True])
async def test_known_scope_keeps_existing_credential_filtering(store, monkeypatch, force):
    # Exercise real try_all, not just the scanner gate, without network calls.
    from modules import bruteforce

    monkeypatch.setattr(SSHMAP, "attempt_store", store)
    monkeypatch.setattr(SSHMAP, "start_host", "local")
    monkeypatch.setattr(SSHMAP, "ssh_ports", [22])
    monkeypatch.setattr(SSHMAP, "graph", None)
    monkeypatch.setattr(SSHMAP, "check_open_port", AsyncMock(return_value=True))
    monkeypatch.setattr(bruteforce, "CONFIG", {"record_connection_attempts": True})
    await record(store, "success", user="old-success")
    await record(store, "auth_failed", user="old-auth")
    await record(store, "session_failed", user="old-session")
    creds = MagicMock()
    creds.get_credentials_host_and_bruteforce.return_value = [
        Credential("_bruteforce", 22, user, "secret", "password")
        for user in ("old-success", "old-auth", "old-session", "new")
    ]

    async def failed(host, port, credential, **kwargs):
        kwargs["_outcome"]["status"] = "auth_failed"
        return None

    single = AsyncMock(side_effect=failed)
    monkeypatch.setattr(bruteforce, "try_single_credential", single)
    await SSHMAP.handle_target("10.0.0.1", 1, creds, 1, known_ssh_only=True, force_rescan=force)
    users = {call.args[2].user for call in single.await_args_list}
    assert users == ({"old-success", "old-auth", "old-session", "new"} if force else {"old-session", "new"})
