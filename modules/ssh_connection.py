import paramiko

class SSHSession:
    def __init__(self, host, user, password=None, key_filename=None):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if key_filename:
            self.client.connect(hostname=host, username=user, key_filename=key_filename)
        else:
            self.client.connect(hostname=host, username=user, password=password)

    def exec_command(self, command):
        stdin, stdout, stderr = self.client.exec_command(command)
        return stdout.read().decode()

    def close(self):
        self.client.close()
