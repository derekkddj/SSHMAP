import paramiko
from .ssh_connection import SSHSession

class Result:
    def __init__(self, user, method, ssh_session):
        self.user = user
        self.method = method
        self.ssh_session = ssh_session

    def get_ssh_connection(self):
        return self.ssh_session

def try_all(host, users, passwords, keyfiles):
    results = []
    for user in users:
        for pwd in passwords:
            try:
                ssh = SSHSession(host, user, password=pwd)
                results.append(Result(user, "password", ssh))
            except Exception:
                continue
        for keyfile in keyfiles:
            try:
                ssh = SSHSession(host, user, key_filename=keyfile)
                results.append(Result(user, "keyfile", ssh))
            except Exception:
                continue
    return results
