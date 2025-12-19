import pytest
import subprocess
import os
import tempfile
import shutil
from modules.graphdb import GraphDB
from modules.credential_store import CredentialStore


class TestE2EFullScan:
    def test_full_scan_docker_network(self, docker_compose, neo4j, temp_csv_yaml):
        """End-to-end test: Run SSHMAP on docker network, verify discoveries"""
        csv_file, yaml_file = temp_csv_yaml

        # Create temp wordlists
        users_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
        users_file.write("root\ntest\n")
        users_file.close()

        passwords_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
        passwords_file.write("root\ntemporal01\nwrongpass\n")
        passwords_file.close()

            # Config YAML - not used, defaults are fine

        # Run SSHMAP scan on localhost (but since containers are on 127.0.0.1:2222 etc, perhaps scan 127.0.0.1 with ports
        # Actually, better to scan the container IPs, but for simplicity, scan a range that includes them, but since docker, use the published ports.

        # Create temp targets file with 127.0.0.1 first, then specified IPs
        targets_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
        targets_file.write("127.0.0.1\n")
        targets_file.close()

        # Create temp blacklist file excluding ranges except specific IPs
        blacklist_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
        # Exclude all 192.168.0.0/16 as CIDR (assuming CIDR support)
        blacklist_file.write("192.168.0.0/16\n")
        # Exclude all 172.18.0.0/24
        for i in range(256):
            blacklist_file.write(f"172.18.0.{i}\n")
        # Exclude all 172.19.0.0/24 except the target IPs
        except_ips = {"172.19.0.2", "172.19.0.3", "172.19.0.4", "172.19.0.5", "172.19.0.6", "172.19.0.106", "172.19.0.107"}
        for i in range(256):
            ip = f"172.19.0.{i}"
            if ip not in except_ips:
                blacklist_file.write(f"{ip}\n")
        blacklist_file.close()

        # Create temp keys directory with machine5_key
        keys_dir = tempfile.mkdtemp()
        with open(os.path.join(keys_dir, "machine5_key"), 'w') as f:
            with open("tests/machine5_key", 'r') as src:
                f.write(src.read())

        # Run SSHMAP
        result = subprocess.run([
            "python3", "SSHMAP.py",
            "--targets", targets_file.name,
            "--blacklist", blacklist_file.name,
            "--users", users_file.name,
            "--passwords", passwords_file.name,
            "--credentialspath", csv_file,
            "--keys", keys_dir,
            "--verbose"
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
        os.unlink(passwords_file.name)
        os.unlink(targets_file.name)
        os.unlink(blacklist_file.name)
        import shutil
        shutil.rmtree(keys_dir)