import csv
import os
from threading import Lock
from dataclasses import dataclass, asdict
from .logger import sshmap_logger
from .utils import preload_key


@dataclass(frozen=True, eq=True)
class Credential:
    remote_ip: str
    port: str
    user: str
    secret: str
    method: str

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(data):
        return Credential(
            remote_ip=data["remote_ip"],
            port=data["port"],
            user=data["user"],
            secret=data["secret"],
            method=data["method"],
        )


class CredentialStore:
    def __init__(self, path="wordlists/credentials.csv"):

        self.path = path
        self.lock = Lock()
        self.key_objects = {}
        sshmap_logger.debug(f"Loading credentials from {self.path}")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.credentials = self._read_all()
        sshmap_logger.debug(
            f"Loaded {len(self.credentials)} credentials from {self.path}"
        )

    def _read_all(self):
        sshmap_logger.debug(f"Loading credentials from {self.path}")
        if not os.path.exists(self.path):
            sshmap_logger.warning(
                f"Credential file {self.path} does not exist. Creating a new one."
            )
            return []
        credentials = []
        with open(self.path, mode="r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cred = Credential.from_dict(row)
                credentials.append(cred)
                # Preload key if method is 'keyfile'
                if cred.method == "keyfile":
                    secret = cred.secret
                    if secret not in self.key_objects:
                        key_obj = preload_key(secret)
                        if key_obj:
                            self.key_objects[secret] = key_obj
                        else:
                            sshmap_logger.warning(f"Failed to preload key: {secret}")
        return credentials

    def _write_all(self, credentials):
        with open(self.path, mode="w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["remote_ip", "port", "user", "secret", "method"]
            )
            writer.writeheader()
            writer.writerows([cred.to_dict() for cred in credentials])

    async def store(self, remote_ip, port, user, secret, method):
        new_cred = Credential(
            remote_ip=str(remote_ip),
            port=str(port),
            user=user,
            secret=secret,
            method=method,
        )
        with self.lock:
            if new_cred not in self.credentials:
                self.credentials.append(new_cred)
                self._write_all(self.credentials)
            if new_cred.method == "keyfile":
                if secret not in self.key_objects:
                    key_obj = preload_key(secret)
                    if key_obj:
                        self.key_objects[secret] = key_obj
            else:
                sshmap_logger.debug(f"Credential already exists: {new_cred}")

    def get_all_method_password(self):
        with self.lock:
            return [cred for cred in self.credentials if cred.method == "password"]

    def get_all_method_keyfile(self):
        with self.lock:
            return [cred for cred in self.credentials if cred.method == "keyfile"]

    def get_triplets(self):
        with self.lock:
            return list(
                {(cred.user, cred.secret, cred.method) for cred in self.credentials}
            )

    def get_credentials_host_and_bruteforce(self, host, port):
        """Return credentials if:
        - The remote_ip matches the given host and port
        - OR the remote_ip is '_bruteforce'
        Deduplicate by (user, secret, method)
        """
        with self.lock:
            seen = set()
            results = []

            for cred in self.credentials:
                if (
                    cred.remote_ip == host and cred.port == str(port)
                ) or cred.remote_ip == "_bruteforce":
                    key = (cred.user, cred.secret, cred.method)
                    if key not in seen:
                        seen.add(key)
                        results.append(cred)

            return results

    def find(self, remote_ip, port):
        with self.lock:
            return [
                cred
                for cred in self.credentials
                if cred.remote_ip == remote_ip and cred.port == str(port)
            ]

    def delete_credentials(self, remote_ip, port):
        with self.lock:
            self.credentials = [
                cred
                for cred in self.credentials
                if not (cred.remote_ip == remote_ip and cred.port == str(port))
            ]
            self._write_all(self.credentials)

    def get_all(self):
        with self.lock:
            return self.credentials

    def count(self):
        """Return the number of credentials in the store."""
        with self.lock:
            return len(self.credentials)

    def get_key_objects(self):
        with self.lock:
            return self.key_objects
