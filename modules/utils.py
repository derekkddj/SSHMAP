import socket
import psutil
import ipaddress
from .logger import sshmap_logger
from .config import CONFIG
import asyncio


def read_targets(file_path):
    """Read IPs or CIDRs from the given file and expand CIDRs into individual IPs."""
    targets = []

    with open(file_path, "r") as file:
        for line in file.readlines():
            line = line.strip()
            if line:  # Skip empty lines
                try:
                    # Check if the line is a valid CIDR block
                    network = ipaddress.IPv4Network(line, strict=False)
                    # If it's a valid CIDR, expand it to individual IPs and add them to targets
                    targets.extend([str(ip) for ip in network.hosts()])
                except ValueError:
                    # If it's not a valid CIDR, treat it as an individual IP
                    targets.append(line)

    return targets


def get_local_info():
    hostname = socket.gethostname()
    ip_info = []

    for iface, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET:
                mask = netmask_to_cidr(addr.netmask)  # Convert netmask to CIDR
                ip_info.append({"ip": addr.address, "mask": mask})

    return hostname, ip_info


def netmask_to_cidr(netmask):
    """Convert dotted-decimal netmask to CIDR notation."""
    return sum([bin(int(x)).count("1") for x in netmask.split(".")])


# ssh_client is an instance of SSHSession
async def get_remote_hostname(ssh_client):
    sshmap_logger.debug("Getting remote hostname...")
    try:
        hostname, err = await ssh_client.exec_command_with_stderr("hostname")
        hostname = (
            hostname.strip()
            if not err
            else ssh_client.connection.get_extra_info("peername")[0]
        )
    except AttributeError as e:
        sshmap_logger.error(f"Failed to get attribute: {e}")
        hostname = ssh_client.host
    except Exception as e:
        sshmap_logger.error(f"Failed to get hostname from {ssh_client.host}: {type(e).__name__} - {e}")
        hostname = ssh_client.host
    return hostname


# ssh_client is an instance of SSHSession
async def get_remote_info(ssh_client):
    sshmap_logger.debug("Getting remote hostname...")
    try:
        hostname, err = await ssh_client.exec_command_with_stderr("hostname")
        hostname = (
            hostname.strip()
            if not err
            else ssh_client.connection.get_extra_info("peername")[0]
        )
    except Exception as e:
        sshmap_logger.error(f"Failed to get hostname: {e}")
        hostname = ssh_client.host

    ip_info = []

    # Try `ip` command first
    out, err = await ssh_client.exec_command_with_stderr(
        "ip -o -4 addr show | awk '{print $4}'"
    )
    if err or not out.strip():
        sshmap_logger.warning(f"`ip` command failed or missing: {err.strip()}")
    else:
        cidrs = out.strip().split()
        for cidr in cidrs:
            if "/" in cidr and "127.0.0.1" not in cidr:
                ip, mask = cidr.split("/")
                ip_info.append({"ip": ip, "mask": int(mask)})

    # Fallback to `ifconfig` if `ip` failed or returned nothing
    if not ip_info:
        out, err = await ssh_client.exec_command_with_stderr("ifconfig")
        if err or not out.strip():
            sshmap_logger.warning(
                f"`ifconfig` command failed or missing: {err.strip()}"
            )
        else:
            lines = out.strip().splitlines()
            current_ip = None
            for line in lines:
                line = line.strip()
                if "inet " in line and "127.0.0.1" not in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "inet":
                            current_ip = parts[i + 1]
                        elif "netmask" in part:
                            netmask = parts[i + 1]
                            try:
                                mask = sum(
                                    [bin(int(x)).count("1") for x in netmask.split(".")]
                                )
                                if current_ip:
                                    ip_info.append({"ip": current_ip, "mask": mask})
                            except Exception as e:
                                sshmap_logger.warning(f"Netmask parse error: {e}")

    # Final fallback
    if not ip_info:
        try:

            peer_ip = ssh_client.connection.get_extra_info("peername")[0]
            if not peer_ip:
                peer_ip = ssh_client.get_host()
            ip_info = [{"ip": peer_ip, "mask": 32}]
        except Exception as e:
            sshmap_logger.error(f"Failed to get peer IP: {e}")
            ip_info = []

    return hostname, ip_info


def in_same_subnet(ip1, mask1, ip2, mask2):
    net1 = ipaddress.ip_network(f"{ip1}/{mask1}", strict=False)
    net2 = ipaddress.ip_network(f"{ip2}/{mask2}", strict=False)
    return net1.overlaps(net2)


def get_all_ips_in_subnet(ip, mask):
    mask = max(mask, CONFIG["max_mask"] if CONFIG["max_mask"] else 24)
    network = ipaddress.ip_network(f"{ip}/{mask}", strict=False)
    return [str(host) for host in network.hosts()]


async def check_open_port(ip, port, timeout=2):
    try:
        # Create the task
        task = asyncio.create_task(_check_open_port(ip, port))

        # Wait with a timeout
        return await asyncio.wait_for(task, timeout=timeout)

    except asyncio.TimeoutError:
        # Timeout handling if the port check takes too long
        return False
    except Exception as e:
        # Catch any other exceptions and handle them gracefully
        sshmap_logger.debug(f"Error checking port {port} on {ip}: {e}")
        return False


async def _check_open_port(ip, port):
    reader, writer = await asyncio.open_connection(ip, port)
    writer.close()
    await writer.wait_closed()
    return True
