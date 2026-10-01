from unittest.mock import MagicMock, patch

import pytest

import SSHMAP


def test_no_recursion_skips_neo4j_and_forces_single_depth():
    argv = ["sshmap", "--targets", "127.0.0.1", "--no-recursion"]

    with patch.object(SSHMAP, "graph", None), \
         patch.object(SSHMAP, "max_depth", 5), \
         patch.object(SSHMAP.sys, "argv", argv), \
         patch.object(SSHMAP.graphdb, "GraphDB") as graph_class, \
         patch.object(SSHMAP, "async_main", new=MagicMock(return_value="scan")) as async_main, \
         patch.object(SSHMAP.asyncio, "run") as asyncio_run:
        SSHMAP.main()
        graph_class.assert_not_called()
        asyncio_run.assert_called_once_with("scan")
        assert async_main.call_args.args[0].no_recursion is True
        assert SSHMAP.max_depth == 1


def test_no_recursion_rejects_start_from():
    argv = [
        "sshmap",
        "--targets",
        "127.0.0.1",
        "--no-recursion",
        "--start-from",
        "jump-host",
    ]

    with patch.object(SSHMAP.sys, "argv", argv), \
         patch.object(SSHMAP.graphdb, "GraphDB") as graph_class, \
         pytest.raises(SystemExit) as exc_info:
        SSHMAP.main()

    assert exc_info.value.code == 2
    graph_class.assert_not_called()
