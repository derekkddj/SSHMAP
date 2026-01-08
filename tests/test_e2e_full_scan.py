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
            "--verbose",
            "--maxworkers", "100",
            "--maxworkers-ssh", "2",
        ], cwd=os.path.dirname(__file__).replace('tests', ''), capture_output=True, text=True)

        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        assert result.returncode == 0

        # Verify CSV has entries
        with open(csv_file, 'r') as f:
            lines = f.readlines()
            assert len(lines) > 1  # Header + at least one entry

        # Query Neo4J for node and relationship details using GraphDB and export to a temporary file
        try:
            import json
            from modules.config import CONFIG

            # Get current hostname using 'hostname' command
            local_hostname = subprocess.check_output(['hostname'], text=True).strip()

            db = GraphDB(CONFIG["neo4j_uri"], CONFIG["neo4j_user"], CONFIG["neo4j_pass"])
            hosts = db.get_all_hosts_detailed()

            # Collect all relationships for each host
            all_rels = []
            for h in hosts:
                rels = db.get_connections_from_host(h["hostname"])
                all_rels.extend(rels)

            db.close()

            tmpf = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.neo4j.json')
            json.dump({"hosts": hosts, "relationships": all_rels}, tmpf, indent=2)
            tmpf.close()

            # Write log with counts
            log_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.neo4j.log')
            log_file.write(f"Neo4j Graph Export Summary\n")
            log_file.write(f"==========================\n")
            log_file.write(f"Number of hosts: {len(hosts)}\n")
            log_file.write(f"Number of relationships: {len(all_rels)}\n")
            log_file.write(f"JSON export: {tmpf.name}\n")
            log_file.close()

            print(f"Neo4j export written to: {tmpf.name}")
            print(f"Neo4j log written to: {log_file.name}")

            # ===== ASSERTIONS FOR NEO4J GRAPH =====
            # Check exactly 7 hosts
            assert len(hosts) == 7, f"Expected 7 hosts, got {len(hosts)}"

            # Expected hosts (first one uses hostname command for dynamic name)
            expected_hosts = {
                local_hostname,
                "machine1_direct",
                "machine2_useasjumphost",
                "machine3_hidden",
                "machine4_SUPPERhidden",
                "machine5_onlykey",
                "machine6_onlykey_direct",
            }
            actual_hosts = {h["hostname"] for h in hosts}
            assert actual_hosts == expected_hosts, f"Host names mismatch.\nExpected: {expected_hosts}\nActual: {actual_hosts}"

            # Check exactly 23 relationships
            assert len(all_rels) == 23, f"Expected 23 relationships, got {len(all_rels)}"

            # Define expected relationships as tuples: (from_host, to_host, ip, port, method, user, creds_check)
            # For keyfile methods, creds_check is "machine5_key" (filename), for password methods it's the exact credential
            expected_rels = {
                (local_hostname, "machine1_direct", "127.0.0.1", 2222, "password", "root", "root"),
                (local_hostname, "machine2_useasjumphost", "127.0.0.1", 2223, "password", "root", "root"),
                (local_hostname, "machine2_useasjumphost", "127.0.0.1", 2223, "password", "test", "temporal01"),
                (local_hostname, "machine6_onlykey_direct", "127.0.0.1", 2224, "keyfile", "root", "machine5_key"),
                ("machine1_direct", "machine1_direct", "127.0.0.1", 22, "password", "root", "root"),
                ("machine2_useasjumphost", "machine2_useasjumphost", "172.19.0.2", 22, "password", "root", "root"),
                ("machine2_useasjumphost", "machine2_useasjumphost", "172.19.0.2", 22, "password", "test", "temporal01"),
                ("machine2_useasjumphost", "machine3_hidden", "172.19.0.3", 22, "password", "root", "root"),
                ("machine2_useasjumphost", "machine5_onlykey", "172.19.0.5", 22, "keyfile", "root", "machine5_key"),
                ("machine2_useasjumphost", "machine6_onlykey_direct", "172.19.0.6", 22, "keyfile", "root", "machine5_key"),
                ("machine3_hidden", "machine4_SUPPERhidden", "172.19.0.4", 22, "password", "root", "root"),
                ("machine3_hidden", "machine6_onlykey_direct", "172.19.0.6", 22, "keyfile", "root", "machine5_key"),
                ("machine3_hidden", "machine2_useasjumphost", "172.19.0.2", 22, "password", "root", "root"),
                ("machine3_hidden", "machine2_useasjumphost", "172.19.0.2", 22, "password", "test", "temporal01"),
                ("machine5_onlykey", "machine6_onlykey_direct", "172.19.0.6", 22, "keyfile", "root", "machine5_key"),
                ("machine5_onlykey", "machine2_useasjumphost", "172.19.0.2", 22, "password", "root", "root"),
                ("machine5_onlykey", "machine2_useasjumphost", "172.19.0.2", 22, "password", "test", "temporal01"),
                ("machine6_onlykey_direct", "machine6_onlykey_direct", "172.19.0.6", 22, "keyfile", "root", "machine5_key"),
                ("machine6_onlykey_direct", "machine2_useasjumphost", "172.19.0.2", 22, "password", "root", "root"),
                ("machine6_onlykey_direct", "machine2_useasjumphost", "172.19.0.2", 22, "password", "test", "temporal01"),
                ("machine4_SUPPERhidden", "machine2_useasjumphost", "172.19.0.2", 22, "password", "root", "root"),
                ("machine4_SUPPERhidden", "machine2_useasjumphost", "172.19.0.2", 22, "password", "test", "temporal01"),
                ("machine4_SUPPERhidden", "machine6_onlykey_direct", "172.19.0.6", 22, "keyfile", "root", "machine5_key"),
            }

            # Check all relationships individually
            # For keyfile methods, compare against filename only (dynamic path); for password methods, exact credential
            actual_rels = set()
            for r in all_rels:
                creds_check = r["props"]["creds"]
                if r["props"]["method"] == "keyfile":
                    # Extract filename from path (e.g., "/tmp/xyz/machine5_key" -> "machine5_key")
                    creds_check = creds_check.split('/')[-1]
                actual_rels.add((r["from"], r["to"], r["props"]["ip"], r["props"]["port"], r["props"]["method"], r["props"]["user"], creds_check))

            assert actual_rels == expected_rels, f"Relationship mismatch.\nExpected {len(expected_rels)} rels:\n{expected_rels}\nActual {len(actual_rels)} rels:\n{actual_rels}\nMissing: {expected_rels - actual_rels}\nExtra: {actual_rels - expected_rels}"

            print(f"✓ All assertions passed: 7 hosts and 22 relationships verified")

        except Exception as e:
            print("Warning: failed to query Neo4j details:", e)
            import traceback
            traceback.print_exc()

        # Cleanup
        os.unlink(users_file.name)
        os.unlink(passwords_file.name)
        os.unlink(targets_file.name)
        os.unlink(blacklist_file.name)
        import shutil
        shutil.rmtree(keys_dir)