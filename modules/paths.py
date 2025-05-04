import os
import sys


SSHMAP_PATH = os.path.expanduser("~/.sshmap")
if os.name == "nt":
    TMP_PATH = os.getenv("LOCALAPPDATA") + "\\Temp\\sshmap_hosted"
    SSHMAP_PATH = os.getenv("APPDATA") + ("\\sshmap")
elif hasattr(sys, "getandroidapilevel"):
    TMP_PATH = os.path.join(
        "/data", "data", "com.termux", "files", "usr", "tmp", "sshmap_hosted"
    )
else:
    TMP_PATH = os.path.join("/tmp", "sshmap_hosted")
