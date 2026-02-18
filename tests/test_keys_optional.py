import pytest
import os
import tempfile
from modules.utils import load_keys

class TestLoadKeys:
    """Test suite for load_keys function in utils.py"""

    def test_load_keys_valid_dir(self):
        """Test loading keys from a valid directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create dummy key files
            with open(os.path.join(temp_dir, "id_rsa"), "w") as f:
                f.write("key1")
            with open(os.path.join(temp_dir, "id_dsa"), "w") as f:
                f.write("key2")
            
            keys = load_keys(temp_dir)
            assert len(keys) == 2
            assert any("id_rsa" in k for k in keys)
            assert any("id_dsa" in k for k in keys)

    def test_load_keys_missing_dir(self):
        """Test loading keys from a missing directory"""
        keys = load_keys("/non/existent/path/to/keys")
        assert keys == []

    def test_load_keys_default_missing(self):
        """Test loading keys from missing default directory (check logging manually or just no crash)"""
        keys = load_keys("wordlists/keys/")
        # If it doesn't exist, should return empty list
        if not os.path.exists("wordlists/keys/"):
            assert keys == []
