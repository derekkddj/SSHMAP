import pytest
import os
import tempfile
from modules.utils import read_targets

class TestReadTargets:
    """Test suite for read_targets function in utils.py"""

    def test_read_from_file(self):
        """Test reading targets from a file"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("192.168.1.1\n")
            f.write("192.168.1.2\n")
            f.flush()
            filename = f.name
        
        try:
            targets = read_targets(filename)
            assert "192.168.1.1" in targets
            assert "192.168.1.2" in targets
            assert len(targets) == 2
        finally:
            if os.path.exists(filename):
                os.unlink(filename)

    def test_read_single_ip(self):
        """Test reading a single IP passed as string"""
        targets = read_targets("10.0.0.1")
        assert len(targets) == 1
        assert "10.0.0.1" in targets

    def test_read_cidr(self):
        """Test reading a CIDR block passed as string"""
        # 192.168.1.0/30 -> .1, .2 (usable hosts)
        targets = read_targets("192.168.1.0/30")
        assert len(targets) == 2
        assert "192.168.1.1" in targets
        assert "192.168.1.2" in targets

    def test_read_invalid_file(self):
        """Test reading from a non-existent file should return empty list or handle error"""
        # It's treated as a string literal which is not a file
        # But wait, logic says: if isfile -> read file. Else treat as string.
        # "non_existent_file.txt" -> treated as string "non_existent_file.txt"
        # Then split by lines (1 line), loop.
        # Try ipnetwork -> ValueError.
        # Except -> append target.
        # So read_targets("foo") -> returns ["foo"]
        # This is expected behavior for hostnames? The original code didn't resolve hostnames in read_targets,
        # it just read IPs/CIDRs. If I pass a hostname, it propagates as a target.
        
        targets = read_targets("non_existent_file.txt")
        assert len(targets) == 1
        assert "non_existent_file.txt" in targets

    def test_read_file_with_cidrs(self):
        """Test reading a file containing CIDRs"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("192.168.1.0/30\n")
            f.flush()
            filename = f.name
        
        try:
            targets = read_targets(filename)
            assert len(targets) == 2
            assert "192.168.1.1" in targets
        finally:
            if os.path.exists(filename):
                os.unlink(filename)
