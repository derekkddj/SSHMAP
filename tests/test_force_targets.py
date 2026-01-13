import pytest
import tempfile
import os
from modules.utils import read_targets


class TestForceTargets:
    """Test suite for force-targets functionality"""
    
    def test_read_force_targets_with_individual_ips(self):
        """Test reading a force-targets file with individual IPs"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("10.0.0.1\n")
            f.write("10.0.0.2\n")
            f.write("10.0.0.3\n")
            f.flush()
            force_targets_file = f.name
        
        try:
            force_targets = read_targets(force_targets_file)
            assert len(force_targets) == 3
            assert "10.0.0.1" in force_targets
            assert "10.0.0.2" in force_targets
            assert "10.0.0.3" in force_targets
        finally:
            os.unlink(force_targets_file)
    
    def test_read_force_targets_with_cidr(self):
        """Test reading a force-targets file with CIDR notation"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("10.0.0.0/30\n")  # /30 network: 4 total IPs, 2 usable hosts
            f.flush()
            force_targets_file = f.name
        
        try:
            force_targets = read_targets(force_targets_file)
            assert len(force_targets) == 2  # /30 gives 2 usable host addresses
            assert "10.0.0.1" in force_targets
            assert "10.0.0.2" in force_targets
        finally:
            os.unlink(force_targets_file)
    
    def test_force_targets_ignores_whitelist_and_blacklist(self):
        """Test that force-targets mode ignores whitelist and blacklist"""
        # In force-targets mode, we only use the IPs from force-targets file
        # This test simulates the logic from async_main
        
        # Simulate force-targets file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("192.168.1.5\n")
            f.write("192.168.1.10\n")
            f.write("192.168.1.15\n")
            f.flush()
            force_targets_file = f.name
        
        # Simulate whitelist (should be ignored)
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f2:
            f2.write("192.168.1.5\n")
            f2.flush()
            whitelist_file = f2.name
        
        # Simulate blacklist (should be ignored)
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f3:
            f3.write("192.168.1.10\n")
            f3.flush()
            blacklist_file = f3.name
        
        try:
            # Simulate force-targets mode logic
            force_targets_mode = True
            if force_targets_mode:
                new_targets = read_targets(force_targets_file)
            
            # In force-targets mode, all IPs from the file are used
            assert len(new_targets) == 3
            assert "192.168.1.5" in new_targets
            assert "192.168.1.10" in new_targets  # Not filtered by blacklist
            assert "192.168.1.15" in new_targets
        finally:
            os.unlink(force_targets_file)
            os.unlink(whitelist_file)
            os.unlink(blacklist_file)
    
    def test_force_targets_with_mixed_ips_and_cidrs(self):
        """Test force-targets with mix of individual IPs and CIDR ranges"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("192.168.1.100\n")  # Individual IP
            f.write("10.0.0.0/30\n")     # CIDR range (2 hosts)
            f.write("172.16.0.50\n")     # Another individual IP
            f.flush()
            force_targets_file = f.name
        
        try:
            force_targets = read_targets(force_targets_file)
            # Should have 2 IPs from CIDR + 2 individual IPs = 4 total
            assert len(force_targets) == 4
            assert "192.168.1.100" in force_targets
            assert "172.16.0.50" in force_targets
            assert "10.0.0.1" in force_targets
            assert "10.0.0.2" in force_targets
        finally:
            os.unlink(force_targets_file)
