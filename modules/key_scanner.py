def find_keys(ssh_session):
    paths = ["~/.ssh", "/home/*/.ssh", "/etc/ssh"]
    keys = []
    for path in paths:
        try:
            out = ssh_session.exec_command(
                f"find {path} -type f -name 'id_*' -exec file {{}} \; 2>/dev/null"
            )
            if out:
                keys.append(out.strip())
        except Exception:
            continue
    # Optionally parse known_hosts
    try:
        known_hosts = ssh_session.exec_command("cat ~/.ssh/known_hosts 2>/dev/null")
        if known_hosts:
            keys.append("Known hosts:\n" + known_hosts.strip())
    except Exception:
        pass
    return keys
