import csv
import os
from threading import Lock
from .logger import sshmap_logger

class CredentialStore:
    def __init__(self, path="wordlists/valid_credentials.csv"):
        self.path = path
        self.lock = Lock()
        self.credentials = self._read_all()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def _read_all(self):
        if not os.path.exists(self.path):
            return []

        with open(self.path, mode="r", newline="") as f:
            reader = csv.DictReader(f)
            return list(reader)

    def _write_all(self, credentials):
        with open(self.path, mode="w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["remote_ip", "port", "user", "secret", "method"])
            writer.writeheader()
            writer.writerows(credentials)

    def store(self, remote_ip, port, user, secret, method):
        new_entry = {
            "remote_ip": remote_ip,
            "port": str(port),
            "user": user,
            "secret": secret,
            "method": method
        }
        """Add or update a credential."""
        with self.lock:
            if not any(
                cred["remote_ip"] == new_entry["remote_ip"] and
                cred["port"] == new_entry["port"] and
                cred["user"] == new_entry["user"] and
                cred["secret"] == new_entry["secret"] and
                cred["method"] == new_entry["method"]
                for cred in self.credentials
            ):
                self.credentials.append(new_entry)
                self._write_all(self.credentials)
            else:
                sshmap_logger.debug(f"Credential already exists: {remote_ip}:{port} - {user}:{secret} ({method})")
                return


    def get_all_method_password(self):
        """Return all stored credentials with method 'password'."""
        with self.lock:
            return [
                cred for cred in self.credentials
                if cred["method"] == "password"
            ]

    def get_all_method_keyfile(self):
        """Return all stored credentials with method 'keyfile'."""
        with self.lock:
            return [
                cred for cred in self.credentials
                if cred["method"] == "keyfile"
            ]

    def get_triplets(self):
        with self.lock:
            return list({(cred["user"], cred["secret"], cred["method"]) for cred in self.credentials})
    
    def get_all(self):
        """Return all stored credentials."""
        with self.lock:
            return self.credentials

    def find(self, remote_ip, port):
        """Find all credentials for a given IP and port."""
        with self.lock:
            return [
                row for row in self.credentials
                if row["remote_ip"] == remote_ip and row["port"] == str(port)
            ]
