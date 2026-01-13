import pytest
import tempfile
import os
from modules.utils import read_targets


class TestWhitelistFiltering:
    """Test suite for whitelist IP filtering functionality"""
    
    def test_read_targets_with_individual_ips(self):
        """Test reading a whitelist file with individual IPs"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("192.168.1.1\n")
            f.write("192.168.1.2\n")
            f.write("192.168.1.3\n")
            f.flush()
            whitelist_file = f.name
        
        try:
            whitelist_ips = read_targets(whitelist_file)
            assert len(whitelist_ips) == 3
            assert "192.168.1.1" in whitelist_ips
            assert "192.168.1.2" in whitelist_ips
            assert "192.168.1.3" in whitelist_ips
        finally:
            os.unlink(whitelist_file)
    
    def test_read_targets_with_cidr(self):
        """Test reading a whitelist file with CIDR notation"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("192.168.1.0/30\n")  # This should expand to 192.168.1.1 and 192.168.1.2
            f.flush()
            whitelist_file = f.name
        
        try:
            whitelist_ips = read_targets(whitelist_file)
            assert len(whitelist_ips) == 2  # /30 gives 2 hosts
            assert "192.168.1.1" in whitelist_ips
            assert "192.168.1.2" in whitelist_ips
        finally:
            os.unlink(whitelist_file)
    
    def test_whitelist_filters_targets(self):
        """Test that whitelist properly filters target IPs"""
        # Create test target list
        targets = ["192.168.1.1", "192.168.1.2", "192.168.1.3", "192.168.1.4", "192.168.1.5"]
        
        # Create whitelist with only some IPs
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("192.168.1.2\n")
            f.write("192.168.1.4\n")
            f.flush()
            whitelist_file = f.name
        
        try:
            whitelist_ips = read_targets(whitelist_file)
            
            # Simulate the filtering logic from async_main
            filtered_targets = [ip for ip in targets if ip in whitelist_ips]
            
            assert len(filtered_targets) == 2
            assert "192.168.1.2" in filtered_targets
            assert "192.168.1.4" in filtered_targets
            assert "192.168.1.1" not in filtered_targets
            assert "192.168.1.3" not in filtered_targets
            assert "192.168.1.5" not in filtered_targets
        finally:
            os.unlink(whitelist_file)
    
    def test_whitelist_with_blacklist(self):
        """Test that whitelist works together with blacklist"""
        # Create test target list
        targets = ["192.168.1.1", "192.168.1.2", "192.168.1.3", "192.168.1.4", "192.168.1.5"]
        
        # Create whitelist
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("192.168.1.2\n")
            f.write("192.168.1.3\n")
            f.write("192.168.1.4\n")
            f.flush()
            whitelist_file = f.name
        
        # Create blacklist
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f2:
            f2.write("192.168.1.3\n")
            f2.flush()
            blacklist_file = f2.name
        
        try:
            whitelist_ips = read_targets(whitelist_file)
            blacklist_ips = read_targets(blacklist_file)
            
            # Simulate the filtering logic from async_main
            filtered_targets = [ip for ip in targets if ip in whitelist_ips and ip not in blacklist_ips]
            
            assert len(filtered_targets) == 2
            assert "192.168.1.2" in filtered_targets
            assert "192.168.1.4" in filtered_targets
            assert "192.168.1.3" not in filtered_targets  # Blacklisted
            assert "192.168.1.1" not in filtered_targets  # Not in whitelist
            assert "192.168.1.5" not in filtered_targets  # Not in whitelist
        finally:
            os.unlink(whitelist_file)
            os.unlink(blacklist_file)
    
    def test_whitelist_with_cidr_and_blacklist(self):
        """Test whitelist with CIDR notation combined with blacklist"""
        # Create test target list - expand 192.168.1.0/29 (8 IPs total, 6 hosts)
        targets = [f"192.168.1.{i}" for i in range(1, 7)]
        
        # Create whitelist with CIDR
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("192.168.1.0/29\n")  # 192.168.1.1-6 hosts
            f.flush()
            whitelist_file = f.name
        
        # Create blacklist
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f2:
            f2.write("192.168.1.3\n")
            f2.write("192.168.1.5\n")
            f2.flush()
            blacklist_file = f2.name
        
        try:
            whitelist_ips = read_targets(whitelist_file)
            blacklist_ips = read_targets(blacklist_file)
            
            # Simulate the filtering logic from async_main
            filtered_targets = [ip for ip in targets if ip in whitelist_ips and ip not in blacklist_ips]
            
            assert len(filtered_targets) == 4
            assert "192.168.1.1" in filtered_targets
            assert "192.168.1.2" in filtered_targets
            assert "192.168.1.4" in filtered_targets
            assert "192.168.1.6" in filtered_targets
            assert "192.168.1.3" not in filtered_targets  # Blacklisted
            assert "192.168.1.5" not in filtered_targets  # Blacklisted
        finally:
            os.unlink(whitelist_file)
            os.unlink(blacklist_file)
    
    def test_no_whitelist_only_blacklist(self):
        """Test that filtering works correctly when no whitelist is provided"""
        # Create test target list
        targets = ["192.168.1.1", "192.168.1.2", "192.168.1.3", "192.168.1.4", "192.168.1.5"]
        
        # Create blacklist only
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("192.168.1.2\n")
            f.write("192.168.1.4\n")
            f.flush()
            blacklist_file = f.name
        
        try:
            whitelist_ips = None  # No whitelist
            blacklist_ips = read_targets(blacklist_file)
            
            # Simulate the filtering logic from async_main when no whitelist
            if whitelist_ips:
                filtered_targets = [ip for ip in targets if ip in whitelist_ips and ip not in blacklist_ips]
            else:
                filtered_targets = [ip for ip in targets if ip not in blacklist_ips]
            
            assert len(filtered_targets) == 3
            assert "192.168.1.1" in filtered_targets
            assert "192.168.1.3" in filtered_targets
            assert "192.168.1.5" in filtered_targets
            assert "192.168.1.2" not in filtered_targets
            assert "192.168.1.4" not in filtered_targets
        finally:
            os.unlink(blacklist_file)
