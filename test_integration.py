#!/usr/bin/env python3
"""
Integration test for the actual get_remote_ip() function in utils.py
This creates a mock SSH client and tests the real implementation
"""

import asyncio
import sys
sys.path.insert(0, './SSHMAP')

from modules.utils import get_remote_ip


class MockSSHClient:
    """Mock SSH client that simulates command execution"""
    
    def __init__(self, host, command_responses):
        self.host = host
        self.command_responses = command_responses
        self.connection = MockConnection()
    
    async def exec_command_with_stderr(self, cmd):
        """Simulate command execution with predefined responses"""
        # Check if command matches any of our responses
        for pattern, (stdout, stderr, exit_status) in self.command_responses.items():
            if pattern in cmd:
                print(f"  [Mock] Executing: {cmd[:60]}...")
                return stdout, stderr, exit_status
        
        # Default: command not found
        return "", "command not found", 127
    
    def get_host(self):
        return self.host


class MockConnection:
    """Mock connection object"""
    
    def get_extra_info(self, key):
        if key == "peername":
            return ("10.0.0.1", 22)
        return None


async def _test_modern_linux():
    """Test modern Linux with 'ip' command"""
    print("\n" + "=" * 70)
    print("TEST 1: Modern Linux System")
    print("=" * 70)
    
    responses = {
        "ip -o -4 addr show": (
            "127.0.0.1/8\n192.168.20.18/24\n192.168.20.25/24\n172.20.0.1/16\n",
            "",
            0
        )
    }
    
    mock_client = MockSSHClient("test-linux-host", responses)
    result = await get_remote_ip(mock_client)
    
    print(f"\nResult: Found {len(result)} IPs")
    for ip_data in result:
        print(f"  ✓ {ip_data['ip']}/{ip_data['mask']}")
    
    # Validate
    expected = [
        {"ip": "192.168.20.18", "mask": 24},
        {"ip": "192.168.20.25", "mask": 24},
        {"ip": "172.20.0.1", "mask": 16},
    ]
    
    # Check loopback was filtered
    loopback_found = any(ip['ip'] == "127.0.0.1" for ip in result)
    if loopback_found:
        print("\n✗ FAILED: Loopback was not filtered!")
        return False
    
    # Check all expected IPs are present
    if len(result) != len(expected):
        print(f"\n✗ FAILED: Expected {len(expected)} IPs, got {len(result)}")
        return False
    
    for i, exp in enumerate(expected):
        if result[i]['ip'] != exp['ip'] or result[i]['mask'] != exp['mask']:
            print(f"\n✗ FAILED: Mismatch at {i}")
            return False
    
    print("\n✓ PASSED: Modern Linux parsing working correctly")
    return True


def test_modern_linux():
    assert asyncio.run(_test_modern_linux())


async def _test_hpux():
    """Test HP-UX with netstat + ifconfig + awk"""
    print("\n" + "=" * 70)
    print("TEST 2: HP-UX System")
    print("=" * 70)
    
    # HP-UX responses: ip command fails, netstat+ifconfig succeeds
    responses = {
        "ip -o -4 addr show": ("", "ip: command not found", 127),
        "for sub_if in": (
            "172.16.49.213/24\n10.65.132.180/16\n10.147.39.155/24\n4.4.4.9/26\n172.16.49.220/24\n",
            "",
            0
        )
    }
    
    mock_client = MockSSHClient("test-hpux-host", responses)
    result = await get_remote_ip(mock_client)
    
    print(f"\nResult: Found {len(result)} IPs")
    for ip_data in result:
        print(f"  ✓ {ip_data['ip']}/{ip_data['mask']}")
    
    # Validate
    expected = [
        {"ip": "172.16.49.213", "mask": 24},
        {"ip": "10.65.132.180", "mask": 16},
        {"ip": "10.147.39.155", "mask": 24},
        {"ip": "4.4.4.9", "mask": 26},  # Critical: must be /26, not /24!
        {"ip": "172.16.49.220", "mask": 24},
    ]
    
    if len(result) != len(expected):
        print(f"\n✗ FAILED: Expected {len(expected)} IPs, got {len(result)}")
        return False
    
    for i, exp in enumerate(expected):
        if result[i]['ip'] != exp['ip'] or result[i]['mask'] != exp['mask']:
            print(f"\n✗ FAILED: Mismatch at {i}: expected {exp['ip']}/{exp['mask']}, got {result[i]['ip']}/{result[i]['mask']}")
            return False
    
    print("\n✓ PASSED: HP-UX parsing working correctly (including accurate /26 mask)")
    return True


def test_hpux():
    assert asyncio.run(_test_hpux())


async def _test_fallback():
    """Test fallback to peer IP when all commands fail"""
    print("\n" + "=" * 70)
    print("TEST 3: Fallback to Peer IP")
    print("=" * 70)
    
    # All commands fail
    responses = {
        "ip -o -4 addr show": ("", "command not found", 127),
        "for sub_if in": ("", "command not found", 127),
        "ifconfig": ("", "command not found", 127),
    }
    
    mock_client = MockSSHClient("test-fallback-host", responses)
    result = await get_remote_ip(mock_client)
    
    print(f"\nResult: Found {len(result)} IPs")
    for ip_data in result:
        print(f"  ✓ {ip_data['ip']}/{ip_data['mask']}")
    
    # Should fallback to peer IP
    if len(result) != 1:
        print(f"\n✗ FAILED: Expected 1 fallback IP, got {len(result)}")
        return False
    
    if result[0]['ip'] != "10.0.0.1" or result[0]['mask'] != 32:
        print(f"\n✗ FAILED: Expected peer IP 10.0.0.1/32, got {result[0]['ip']}/{result[0]['mask']}")
        return False
    
    print("\n✓ PASSED: Fallback to peer IP working correctly")
    return True


def test_fallback():
    assert asyncio.run(_test_fallback())


async def main():
    print("\n" + "=" * 70)
    print("INTEGRATION TEST: Real get_remote_ip() from utils.py")
    print("=" * 70)
    
    test1 = await _test_modern_linux()
    test2 = await _test_hpux()
    test3 = await _test_fallback()
    
    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)
    print(f"  Test 1 (Modern Linux): {'✓ PASSED' if test1 else '✗ FAILED'}")
    print(f"  Test 2 (HP-UX):        {'✓ PASSED' if test2 else '✗ FAILED'}")
    print(f"  Test 3 (Fallback):     {'✓ PASSED' if test3 else '✗ FAILED'}")
    
    if test1 and test2 and test3:
        print("\n✓ ALL INTEGRATION TESTS PASSED!")
        print("  The actual get_remote_ip() implementation is working correctly!")
        return 0
    else:
        print("\n✗ SOME TESTS FAILED - Check the implementation!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
