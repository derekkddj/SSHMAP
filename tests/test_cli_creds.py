import pytest
import os
import tempfile
from modules.utils import read_list_from_file_or_string

class TestReadListFromFileOrString:
    """Test suite for read_list_from_file_or_string function in utils.py"""

    def test_read_from_file(self):
        """Test reading lines from a valid file"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("user1\n")
            f.write("user2\n")
            f.flush()
            filename = f.name
        
        try:
            result = read_list_from_file_or_string(filename)
            assert len(result) == 2
            assert "user1" in result
            assert "user2" in result
        finally:
            if os.path.exists(filename):
                os.unlink(filename)

    def test_read_direct_string(self):
        """Test reading a direct string input"""
        result = read_list_from_file_or_string("root")
        assert len(result) == 1
        assert "root" in result

    def test_read_non_existent_file(self):
        """Test reading a non-existent file path, should treat as string"""
        # This matches the behavior we want: if I say --users "foo.txt" and it doesn't exist,
        # it might be a weird username but we treat it as a username "foo.txt".
        result = read_list_from_file_or_string("non_existent_file.txt")
        assert len(result) == 1
        assert "non_existent_file.txt" in result

    def test_empty_input(self):
        """Test empty input handling"""
        assert read_list_from_file_or_string(None) == []
        assert read_list_from_file_or_string("") == []
