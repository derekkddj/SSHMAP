import pytest
import os
import tempfile
import shutil
from unittest.mock import MagicMock, patch, AsyncMock
from modules.post_exploitation.modules.linpeas import LinPEASModule

@pytest.mark.asyncio
async def test_linpeas_downloads_if_missing():
    """Test that LinPEAS downloads if local file is missing"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Override wordlists dir for testing
        with patch("modules.post_exploitation.modules.linpeas.os.makedirs") as mock_makedirs, \
             patch("modules.post_exploitation.modules.linpeas.urllib.request.urlretrieve") as mock_download, \
             patch("modules.post_exploitation.modules.linpeas.os.path.exists") as mock_exists, \
             patch("modules.post_exploitation.modules.linpeas.asyncssh.scp", new_callable=AsyncMock) as mock_scp:
            
            # Setup mocks
            # checking wordlists dir -> False (create it)
            # checking linpeas.sh -> False (download it)
            # checking local_linpeas_path before cleanup -> True (but we removed cleanup so this might not matter)
            mock_exists.side_effect = lambda p: False if "linpeas.sh" in p else True
            
            module = LinPEASModule()
            ssh_session = MagicMock()
            ssh_session.get_remote_hostname.return_value = "target"
            ssh_session.exec_command = AsyncMock(return_value="HAS_TIMEOUT")
            
            # Run execute
            await module.execute(ssh_session, temp_dir)
            
            # Verify download was called
            mock_download.assert_called_once()
            args, _ = mock_download.call_args
            assert "linpeas.sh" in args[0] # URL
            assert "wordlists/linpeas.sh" in args[1] # Path

@pytest.mark.asyncio
async def test_linpeas_skips_download_if_present():
    """Test that LinPEAS skips download if local file exists"""
    with tempfile.TemporaryDirectory() as temp_dir:
        with patch("modules.post_exploitation.modules.linpeas.os.makedirs"), \
             patch("modules.post_exploitation.modules.linpeas.urllib.request.urlretrieve") as mock_download, \
             patch("modules.post_exploitation.modules.linpeas.os.path.exists") as mock_exists, \
             patch("modules.post_exploitation.modules.linpeas.asyncssh.scp", new_callable=AsyncMock) as mock_scp:
            
            # Setup mocks
            # checking linpeas.sh -> True (skip download)
            mock_exists.side_effect = lambda p: True
            
            module = LinPEASModule()
            ssh_session = MagicMock()
            ssh_session.get_remote_hostname.return_value = "target"
            ssh_session.exec_command = AsyncMock(return_value="HAS_TIMEOUT")
            
            # Run execute
            await module.execute(ssh_session, temp_dir)
            
            # Verify download was NOT called
            mock_download.assert_not_called()


