import pytest
import subprocess
import os
import tempfile
from modules.graphdb import GraphDB
from modules.credential_store import CredentialStore


class TestE2EFullScan:
    def test_full_scan_docker_network(self, docker_compose, temp_csv_yaml):
        """End-to-end test: Run SSHMAP on docker network, verify discoveries"""
        csv_file, yaml_file = temp_csv_yaml

        # Create temp wordlists
        users_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
        users_file.write("root\ntest\n")
        users_file.close()

        passwords_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
        passwords_file.write("root\ntemporal01\nwrongpass\n")
        passwords_file.close()

        # Config YAML
        config_content = f"""
scan_timeout: 10
wordlist_users: {users_file.name}
wordlist_passwords: {passwords_file.name}
wordlist_keys: /dev/null
neo4j_uri: bolt://localhost:7687
neo4j_user: neo4j
neo4j_password: password
max_workers: 5
depth: 1
"""
        with open(yaml_file, 'w') as f:
            f.write(config_content)

        # Run SSHMAP scan on localhost (but since containers are on 127.0.0.1:2222 etc, perhaps scan 127.0.0.1 with ports
        # Actually, better to scan the container IPs, but for simplicity, scan a range that includes them, but since docker, use the published ports.

        # For e2e, run with targets like 127.0.0.1:2222,127.0.0.1:2223
        targets = "127.0.0.1:2222,127.0.0.1:2223"

        # Run SSHMAP
        result = subprocess.run([
            "python", "SSHMAP.py",
            "--targets", targets,
            "--config", yaml_file,
            "--csv", csv_file
        ], cwd=os.path.dirname(__file__).replace('tests', ''), capture_output=True, text=True)

        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        assert result.returncode == 0

        # Verify CSV has entries
        with open(csv_file, 'r') as f:
            lines = f.readlines()
            assert len(lines) > 1  # Header + at least one entry

        # Verify graph has hosts (if neo4j running, but for test, perhaps mock or check if entries)

        # Cleanup
        os.unlink(users_file.name)
        os.unlink(passwords_file.name)</content>
<parameter name="filePath">tests/test_e2e_full_scan.py