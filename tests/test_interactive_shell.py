import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import argparse
import asyncio
# We import sys to mock modules if needed, but here we patch logging/subprocess
import sys

# Import logic to test
from sshmap_execute import main, async_main

def test_interactive_shell_validation():
    # Test main() validation logic
    with patch("sshmap_execute.sshmap_logger") as mock_logger, \
         patch("sshmap_execute.graph") as mock_graph, \
         patch("sshmap_execute.asyncio.run") as mock_run, \
         patch("argparse.ArgumentParser.parse_args") as mock_parse_args:
         
        mock_graph.driver.verify_connectivity.return_value = None

        # Case 1: --shell and --all
        mock_parse_args.return_value = argparse.Namespace(
            hostname=None, command=None, all=True, credentialspath="creds",
            debug=False, verbose=False, maxworkers=1, output="out",
            quiet=False, no_store=False, proxy=None, shell=True
        )
        main()
        mock_logger.error.assert_called_with("--shell cannot be used with --all. Please specify a single target with --hostname.")
        mock_run.assert_not_called()

        # Case 2: --shell without --hostname
        mock_parse_args.return_value = argparse.Namespace(
            hostname=None, command=None, all=False, credentialspath="creds",
            debug=False, verbose=False, maxworkers=1, output="out",
            quiet=False, no_store=False, proxy=None, shell=True
        )
        main()
        mock_logger.error.assert_called_with("--shell requires --hostname.")
        mock_run.assert_not_called()

        # Case 3: No --shell and no --command
        mock_parse_args.return_value = argparse.Namespace(
            hostname="host", command=None, all=False, credentialspath="creds",
            debug=False, verbose=False, maxworkers=1, output="out",
            quiet=False, no_store=False, proxy=None, shell=False
        )
        main()
        mock_logger.error.assert_called_with("--command is required unless --shell is specified.")
        mock_run.assert_not_called()

@pytest.mark.asyncio
async def test_interactive_shell_execution():
    # Test async_main execution flow for --shell
    args = argparse.Namespace(
        hostname="192.168.1.1", command=None, all=False, credentialspath="creds",
        debug=False, verbose=False, maxworkers=1, output="out",
        quiet=False, no_store=False, proxy=None, shell=True
    )
    
    with patch("sshmap_execute.setup_debug_logging"), \
         patch("sshmap_execute.CredentialStore"), \
         patch("sshmap_execute.subprocess.run") as mock_subprocess, \
         patch("sshmap_execute.sshmap_logger"), \
         patch("sshmap_execute.graph"), \
         patch("sshmap_execute.SSHSessionManager") as mock_manager_cls:
         
        mock_subprocess.return_value.stdout = "localhost"
        
        mock_session = AsyncMock()
        mock_manager = MagicMock()
        mock_manager.get_session = AsyncMock(return_value=mock_session)
        mock_manager_cls.return_value = mock_manager
        
        await async_main(args)
        
        mock_session.interactive_shell.assert_awaited_once()
        mock_session.exec_command.assert_not_awaited()
