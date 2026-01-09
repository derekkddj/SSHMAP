import pytest
import subprocess
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock
from modules.credential_store import CredentialStore, Credential
from modules.SSHSession import SSHSession


@pytest.fixture
def dummy_store():
    store = CredentialStore()
    # Manually add a credential without using the async store method
    cred = Credential("127.0.0.1", "22", "testuser", "testpass", "password")
    store.credentials.append(cred)
    return store


@pytest.fixture(scope="session")
def docker_compose():
    """Session-scoped fixture to start/stop docker-compose for integration tests."""
    # Assume docker-compose.yaml is in tests/ directory
    compose_dir = os.path.dirname(__file__)
    try:
        import time
        subprocess.run(["docker", "compose", "up", "-d"], cwd=compose_dir, check=True, capture_output=True)
        time.sleep(16)  # Wait for containers to initialize
        # Wait for containers to be ready
        import socket
        ports = [2222, 2223, 2224]
        for port in ports:
            for _ in range(45):  # Wait up to 45 seconds
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    sock.settimeout(5)
                    sock.connect(('127.0.0.1', port))
                    banner = sock.recv(100)
                    if banner.startswith(b"SSH-"):
                        break
                except Exception:
                    pass
                finally:
                    sock.close()
                time.sleep(1)
            else:
                raise Exception(f"SSH on port {port} not ready after 45 seconds")
        time.sleep(5)  # Brief extra wait for internal services
        yield
    finally:
        subprocess.run(["docker", "compose", "down"], cwd=compose_dir, capture_output=True)


@pytest.fixture(scope="session")
def neo4j():
    """Session-scoped fixture to start/stop Neo4J container for e2e tests."""
    import subprocess
    import time
    container_id = None
    try:
        # Remove any existing container with the same name
        subprocess.run(["docker", "rm", "-f", "test-neo4j"], capture_output=True)
        result = subprocess.run([
            "docker", "run", "-d", "--name", "test-neo4j", "--env=NEO4J_AUTH=none",
            "--publish=7474:7474", "--publish=7687:7687",
            "-e", "NEO4J_apoc_export_file_enabled=true",
            "-e", "NEO4J_apoc_import_file_enabled=true",
            "-e", "NEO4J_apoc_import_file_use__neo4j__config=true",
            "-e", "NEO4JLABS_PLUGINS=[\"apoc\"]",
            "neo4j"
        ], capture_output=True, text=True)
        if result.returncode != 0:
            pytest.skip(f"Failed to start Neo4J container: {result.stderr}")
        container_id = result.stdout.strip()

        # Wait for Neo4J to be ready
        time.sleep(30)

        yield container_id
    finally:
        if container_id:
            subprocess.run(["docker", "stop", container_id], capture_output=True)
            subprocess.run(["docker", "rm", container_id], capture_output=True)


@pytest.fixture
def mock_ssh_session():
    """Factory fixture for mocked SSHSession."""
    def _mock_session(connected=True, exec_result="mock output"):
        session = MagicMock(spec=SSHSession)
        session.connect = AsyncMock(return_value=connected)
        session.exec_command = AsyncMock(return_value=exec_result)
        session.close = AsyncMock()
        session.is_connected = connected
        return session
    return _mock_session


@pytest.fixture
def dummy_creds():
    """Fixture with credentials matching docker containers."""
    return [
        Credential("172.19.0.2", "22", "root", "root", "password"),  # machine2
        Credential("172.19.0.3", "22", "root", "root", "password"),  # machine3
        Credential("172.19.0.5", "22", "root", "", "keyfile"),  # machine5
    ]


@pytest.fixture
def temp_csv_yaml():
    """Fixture for temporary CSV and YAML files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_file = os.path.join(tmpdir, "creds.csv")
        yaml_file = os.path.join(tmpdir, "config.yml")
        yield csv_file, yaml_file
