import re
import logging

from modules.logger import NXCAdapter, adjust_log_verbosity, set_log_verbosity, sshmap_logger


def test_protocol_format_includes_time():
    logger = NXCAdapter(
        extra={
            "protocol": "SSH",
            "host": "172.20.208.153",
            "port": 22,
            "hostname": "tehux139",
        }
    )

    formatted, _ = logger.format("[-] [e8e4b6aa-e] root:root")

    assert re.match(r"^\d{2}:\d{2}:\d{2} ", formatted)
    assert "SSH" in formatted
    assert "172.20.208.153" in formatted
    assert "tehux139" in formatted
    assert "root:root" in formatted


def test_adjust_log_verbosity_cycles_between_quiet_verbose_debug():
    original_level = sshmap_logger.logger.getEffectiveLevel()

    try:
        set_log_verbosity("quiet")
        assert sshmap_logger.logger.getEffectiveLevel() == logging.ERROR

        assert adjust_log_verbosity(1) == "verbose"
        assert sshmap_logger.logger.getEffectiveLevel() == logging.INFO

        assert adjust_log_verbosity(1) == "debug"
        assert sshmap_logger.logger.getEffectiveLevel() == logging.DEBUG

        assert adjust_log_verbosity(1) == "debug"
        assert sshmap_logger.logger.getEffectiveLevel() == logging.DEBUG

        assert adjust_log_verbosity(-1) == "verbose"
        assert sshmap_logger.logger.getEffectiveLevel() == logging.INFO

        assert adjust_log_verbosity(-1) == "quiet"
        assert sshmap_logger.logger.getEffectiveLevel() == logging.ERROR
    finally:
        sshmap_logger.logger.setLevel(original_level)
