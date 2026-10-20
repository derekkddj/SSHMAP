"""SSH attempt classifications (auth_failed means rejection, not a wrong secret)."""
import asyncio
import asyncssh


ATTEMPT_STATUSES = frozenset({
    "success", "auth_failed", "connection_failed", "timeout", "session_failed", "unknown",
})


def classify_attempt_error(error, authenticated=False):
    # Once login completed, failures belong to session setup, not authentication.
    if authenticated:
        return "session_failed"
    if isinstance(error, asyncio.TimeoutError):
        return "timeout"
    if isinstance(error, asyncssh.PermissionDenied):
        # May also mean account policy, unsupported auth method, or MFA requirements.
        return "auth_failed"
    if isinstance(error, (FileNotFoundError, PermissionError)):
        return "unknown"  # Local key/configuration problems are not remote rejection.
    if isinstance(error, (asyncssh.ChannelOpenError, asyncssh.DisconnectError,
                          asyncssh.ProtocolError, ConnectionError, OSError)):
        return "connection_failed"
    return "unknown"
