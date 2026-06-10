from modules.utils import get_all_ips_in_subnet


def build_recursive_targets(
    interfaces,
    blacklist_ips=None,
    whitelist_ips=None,
    force_targets_mode=False,
    force_targets_ips=None,
):
    blacklist_ips = blacklist_ips or []

    if force_targets_mode and force_targets_ips:
        return list(set(force_targets_ips))

    new_targets = []
    for interface in interfaces or []:
        if "/" not in interface:
            continue

        ip, mask = interface.split("/", 1)
        try:
            new_targets.extend(get_all_ips_in_subnet(ip, int(mask)))
        except ValueError:
            continue

    new_targets = list(set(new_targets))
    new_targets = [ip for ip in new_targets if ip not in blacklist_ips]

    if whitelist_ips:
        new_targets = [ip for ip in new_targets if ip in whitelist_ips]

    return new_targets


def get_previous_pivot_seed_plans(
    graphdb,
    start_hostname,
    max_depth,
    blacklist_ips=None,
    whitelist_ips=None,
    force_targets_mode=False,
    force_targets_ips=None,
):
    if max_depth <= 1:
        return []

    pivot_plans = []
    seen_hosts = set()
    previous_connections = graphdb.get_connections_from_host(start_hostname) or []

    for connection in previous_connections:
        remote_hostname = connection.get("to")
        if not remote_hostname or remote_hostname in seen_hosts:
            continue

        host_info = graphdb.get_host(remote_hostname)
        if not host_info:
            continue

        targets = build_recursive_targets(
            host_info.get("interfaces") or [],
            blacklist_ips=blacklist_ips,
            whitelist_ips=whitelist_ips,
            force_targets_mode=force_targets_mode,
            force_targets_ips=force_targets_ips,
        )
        if not targets:
            continue

        pivot_plans.append({"hostname": remote_hostname, "targets": targets})
        seen_hosts.add(remote_hostname)

    return pivot_plans