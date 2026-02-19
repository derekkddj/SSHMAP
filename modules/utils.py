import socket
import os
import psutil
import ipaddress
from .logger import sshmap_logger
from .config import CONFIG
import asyncio
import asyncssh
import socks  # PySocks

def create_proxy_socket(proxy_url, target_host, target_port):
    """
    Creates a socket connected to the target host through the proxy.
    Returns the connected socket.
    """
    try:
        from urllib.parse import urlparse
        parsed = urlparse(proxy_url)
        
        proxy_type = socks.SOCKS5
        if parsed.scheme == "socks4":
            proxy_type = socks.SOCKS4
        elif parsed.scheme == "http":
            proxy_type = socks.HTTP
        
        proxy_host = parsed.hostname
        proxy_port = parsed.port
        if not proxy_port:
             if proxy_type == socks.HTTP:
                 proxy_port = 8080
             else:
                 proxy_port = 1080
        
        # Create a socket that goes through the proxy
        s = socks.socksocket()
        s.set_proxy(proxy_type, proxy_host, proxy_port)
        
        # Connect to the target
        s.connect((target_host, target_port))
        return s
    except Exception as e:
        sshmap_logger.error(f"Failed to connect via proxy {proxy_url}: {e}")
        return None


def read_targets(target_input):
    """Read IPs or CIDRs from the given file OR direct string and expand CIDRs into individual IPs."""
    targets = []
    lines = []

    # Check if input is a file
    if os.path.isfile(target_input):
        try:
            with open(target_input, "r") as file:
                lines = [line.strip() for line in file.readlines() if line.strip()]
        except Exception as e:
            sshmap_logger.error(f"Error reading file {target_input}: {e}")
            return []
    else:
        # Treat as direct input (IP or CIDR)
        lines = [target_input.strip()]

    for line in lines:
        try:
            # Check if the line is a valid CIDR block
            network = ipaddress.IPv4Network(line, strict=False)
            # If it's a valid CIDR, expand it to individual IPs and add them to targets
            targets.extend([str(ip) for ip in network.hosts()])
        except ValueError:
            # If it's not a valid CIDR, treat it as an individual IP
            targets.append(line)

    return targets


def read_list_from_file_or_string(input_val):
    """
    Read a list of strings from a file (if valid path) or treat input as a single item list.
    Useful for username/password inputs that could be a file path or the value itself.
    """
    if not input_val:
        return []

    if os.path.isfile(input_val):
        try:
            with open(input_val, "r") as f:
                return [line.strip() for line in f.readlines() if line.strip()]
        except Exception as e:
            sshmap_logger.error(f"Error reading file {input_val}: {e}")
            return []
    else:
        # Treat as direct input
        return [input_val.strip()]


def load_keys(keys_dir):
    """
    Load key file paths from the given directory.
    If the directory does not exist, return an empty list.
    """
    keyfiles = []
    if os.path.isdir(keys_dir):
        try:
            keyfiles = [os.path.abspath(os.path.join(keys_dir, f)) for f in os.listdir(keys_dir)]
        except Exception as e:
            sshmap_logger.error(f"Error listing keys directory {keys_dir}: {e}")
    else:
        if keys_dir != "wordlists/keys/":
             sshmap_logger.warning(f"Keys directory not found: {keys_dir}. proceeding without keys.")
        else:
             sshmap_logger.debug(f"Default keys directory not found: {keys_dir}. proceeding without keys.")
    
    return keyfiles


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


def preload_key(key_filename):
    """
    Loads a single private key using asyncssh.
    """
    try:
        return asyncssh.read_private_key(key_filename)
    except (asyncssh.KeyImportError, asyncssh.KeyEncryptionError) as e:
        sshmap_logger.error(f"[!] Could not load key {key_filename}: {e}")
        return None


# ssh_client is an instance of SSHSession
async def get_remote_hostname(ssh_client):
    sshmap_logger.debug("Getting remote hostname...")
    retries = 3
    for attempt in range(retries):
        try:
            hostname, err, exit_status = await ssh_client.exec_command_with_stderr("hostname")
            # Strip whitespace and validate hostname
            if hostname and hostname.strip():
                hostname = hostname.strip()
                sshmap_logger.debug(f"Successfully retrieved hostname: {hostname}")
                return hostname
            else:
                # hostname command returned empty
                retry_delay = 0.2 if attempt == 0 else 1.0
                sshmap_logger.debug(
                    f"Hostname command returned empty for {ssh_client.host}, exit_status: {exit_status}, stderr: {err}, stdout: {hostname}. Attempt {attempt + 1}/{retries}. Retrying in {retry_delay}s..."
                )
                if attempt < retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
        except Exception as e:
            retry_delay = 0.2 if attempt == 0 else 1.0
            sshmap_logger.warning(f"Error getting hostname on attempt {attempt + 1}: {e}. Retrying in {retry_delay}s...")
            if attempt < retries - 1:
                await asyncio.sleep(retry_delay)
                continue

    # If we get here, all retries failed
    sshmap_logger.warning(f"Failed to get hostname after {retries} attempts.")
    # Still try to return a valid hostname, use IP only as absolute last resort
    # For now, use IP but this indicates a problem
    hostname = ssh_client.host
    sshmap_logger.warning(f"Using IP address as hostname: {hostname}")
    return hostname


# ssh_client is an instance of SSHSession
async def get_remote_ip(ssh_client):
    sshmap_logger.debug(f"Getting remote IP addresses for {ssh_client.host}")
    ip_info = []

    # Try `ip` command first
    out, err = await ssh_client.exec_command_with_stderr(
        "ip -o -4 addr show | awk '{print $4}'"
    )
    if err or not out.strip():
        sshmap_logger.warning(f"`ip` command failed or missing: {err.strip()}")
    else:
        sshmap_logger.debug(f"ip command output: {out}")
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

    return ip_info


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
