"""
cato/tools/conduit_bridge.py — Opt-in browser engine backed by local billing ledger.

Drop-in replacement for browser.py when conduit_enabled=true in config.
Uses the same action interface as BrowserTool but tracks per-action costs
in a local SQLite ledger (no external server required).

Ed25519 identity key is stored in {data_dir}/conduit_identity.key for audit
trail integrity. Billing is recorded in cato.db table conduit_billing.

Action costs:
    All actions = 0 cents (billing disabled for local Cato use)

VOIX protocol: strips <tool>...</tool> and <context>...</context> tags
from extracted HTML/text content before returning to agent.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACTION_COSTS: dict[str, int] = {
    "navigate":   0,
    "click":      0,
    "type":       0,
    "extract":    0,
    "screenshot": 0,
}

_VOIX_TAGS_RE = re.compile(r"<(tool|context)>.*?</(tool|context)>", re.DOTALL)

_BILLING_SCHEMA = """
CREATE TABLE IF NOT EXISTS conduit_billing (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    action      TEXT    NOT NULL,
    cost_cents  INTEGER NOT NULL DEFAULT 0,
    timestamp   REAL    NOT NULL,
    url_or_sel  TEXT    NOT NULL DEFAULT '',
    success     INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_conduit_session ON conduit_billing(session_id);
"""


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class BudgetExceededError(RuntimeError):
    """Raised when a Conduit action would exceed the per-session budget."""


# ---------------------------------------------------------------------------
# Ed25519 identity (local keypair)
# ---------------------------------------------------------------------------

class ConduitIdentity:
    """
    Manages a local Ed25519 keypair stored in {data_dir}/conduit_identity.key.

    The key is used to sign audit receipts — it never leaves the local machine.
    """

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        from ..platform import get_data_dir
        self._key_path = (data_dir or get_data_dir()) / "conduit_identity.key"
        self._private_key: Optional[bytes] = None
        self._public_key: Optional[bytes] = None

    def _load_or_create(self) -> None:
        """Load existing keypair or generate a new one (private implementation)."""
        if self._private_key is not None:
            return

        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import (
                Encoding, PrivateFormat, NoEncryption, PublicFormat,
            )

            if self._key_path.exists():
                raw = self._key_path.read_bytes()
                private_key = Ed25519PrivateKey.from_private_bytes(raw)
            else:
                private_key = Ed25519PrivateKey.generate()
                raw = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
                self._key_path.parent.mkdir(parents=True, exist_ok=True)
                self._key_path.write_bytes(raw)
                self._key_path.chmod(0o600)
                logger.info("ConduitIdentity: new Ed25519 keypair generated at %s", self._key_path)

            self._private_key = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
            pub = private_key.public_key()
            self._public_key = pub.public_bytes(Encoding.Raw, PublicFormat.Raw)

        except ImportError:
            logger.warning("cryptography library unavailable — identity signing disabled")
            self._private_key = b"\x00" * 32
            self._public_key = b"\x00" * 32

    # Public alias so callers don't need to know the underscore convention
    def load_or_create(self) -> None:
        """Public alias for _load_or_create — load or generate the Ed25519 keypair."""
        self._load_or_create()

    @property
    def public_key_hex(self) -> str:
        """Return the public key as a 64-character hex string (property)."""
        self._load_or_create()
        return (self._public_key or b"").hex()

    def public_key_hex_method(self) -> str:
        """Backward-compat method form — prefer the property."""
        return self.public_key_hex

    def sign(self, payload: bytes) -> bytes:
        """Sign payload with the Ed25519 private key."""
        self._load_or_create()
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            pk = Ed25519PrivateKey.from_private_bytes(self._private_key)
            return pk.sign(payload)
        except Exception as exc:
            logger.warning("Ed25519 signing failed: %s", exc)
            return b""


# ---------------------------------------------------------------------------
# Billing ledger
# ---------------------------------------------------------------------------

class ConduitBillingLedger:
    """Append-only SQLite billing ledger stored in cato.db."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        from ..platform import get_data_dir
        self._db_path = db_path or (get_data_dir() / "cato.db")
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_BILLING_SCHEMA)
        self._conn.commit()

    def record(
        self,
        session_id: str,
        action: str,
        cost_cents: int,
        url_or_selector: str = "",
        identity_or_success: "Any" = True,
    ) -> None:
        """Record one billing event.

        The 5th argument accepts either:
        - bool / int — success flag (original internal usage)
        - ConduitIdentity — identity object passed by audit spec callers (ignored;
          the local ledger does not need to verify the identity signature)
        """
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        # Normalize the 5th arg: if it's a bool/int use it; otherwise treat as success=True
        if isinstance(identity_or_success, (bool, int)):
            success_flag = int(bool(identity_or_success))
        else:
            success_flag = 1  # identity object passed — default success
        self._conn.execute(
            "INSERT INTO conduit_billing (session_id, action, cost_cents, timestamp, url_or_sel, success)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, action, cost_cents, time.time(), url_or_selector, success_flag),
        )
        self._conn.commit()

    def session_total(self, session_id: str) -> int:
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT COALESCE(SUM(cost_cents), 0) FROM conduit_billing WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row[0]) if row else 0

    def session_total_cents(self, session_id: str) -> int:
        """Alias for session_total — returns total cents spent in session."""
        return self.session_total(session_id)


# ---------------------------------------------------------------------------
# VOIX helpers
# ---------------------------------------------------------------------------

def _strip_voix_tags(html: str) -> str:
    """Remove <tool>...</tool> and <context>...</context> tags from extracted content."""
    return _VOIX_TAGS_RE.sub("", html).strip()


# ---------------------------------------------------------------------------
# ConduitBridge
# ---------------------------------------------------------------------------

class ConduitBridge:
    """
    Opt-in browser engine with per-action cost tracking.

    Implements the same async interface as BrowserTool but charges per action
    and enforces a per-session budget cap.

    Two supported constructor styles::

        # Style 1 — keyword args (preferred):
        bridge = ConduitBridge(session_id="sess-001", budget_cents=100)

        # Style 2 — config dict + session_id positional (used by agent_loop/CLI):
        bridge = ConduitBridge({"conduit_budget_per_session": 100, "data_dir": "/tmp"}, "sess-001")

        await bridge.start()
        result = await bridge.navigate("https://example.com")
        await bridge.stop()
    """

    def __init__(
        self,
        session_id_or_config: "str | dict" = "default",
        session_id_if_config: str = "",
        budget_cents: int = 100,
        data_dir: Optional[Path] = None,
    ) -> None:
        # Support both call styles:
        #   ConduitBridge("sess-id", budget_cents=100)
        #   ConduitBridge({"conduit_budget_per_session": 100, "data_dir": ...}, "sess-id")
        if isinstance(session_id_or_config, dict):
            cfg = session_id_or_config
            self._session_id = session_id_if_config or "default"
            self._budget_cents = int(cfg.get("conduit_budget_per_session", budget_cents))
            raw_data_dir = cfg.get("data_dir")
            data_dir = Path(raw_data_dir) if raw_data_dir else data_dir
        else:
            self._session_id = str(session_id_or_config)
            self._budget_cents = budget_cents

        self._session_cost_cents_total: int = 0

        self._identity = ConduitIdentity(data_dir)
        # Pass data_dir-based db_path so tests using tmp_path get an isolated ledger
        # instead of writing to the global ~/.cato/cato.db.
        ledger_db = (data_dir / "cato.db") if data_dir is not None else None
        self._ledger = ConduitBillingLedger(db_path=ledger_db)

        # Underlying browser (lazy init)
        self._browser_tool: Optional[Any] = None

        # Track last navigated URL so extract() can re-navigate if needed
        self._current_url: str = ""

    # ------------------------------------------------------------------
    # Public accessors for identity and ledger (used by audit/test code)
    # ------------------------------------------------------------------

    @property
    def identity(self) -> ConduitIdentity:
        return self._identity

    @identity.setter
    def identity(self, value: ConduitIdentity) -> None:
        self._identity = value

    @property
    def ledger(self) -> ConduitBillingLedger:
        return self._ledger

    @ledger.setter
    def ledger(self, value: ConduitBillingLedger) -> None:
        self._ledger = value

    async def start(self) -> None:
        """Initialize the browser and billing ledger."""
        self._ledger.connect()
        # Lazy import to avoid circular deps
        from ..tools.browser import BrowserTool
        self._browser_tool = BrowserTool()
        logger.info(
            "ConduitBridge started — session=%s budget=%dc identity=%s",
            self._session_id, self._budget_cents, self._identity.public_key_hex[:16] + "...",
        )

    async def stop(self) -> None:
        """Gracefully close the browser."""
        if self._browser_tool:
            try:
                await self._browser_tool.close()
            except Exception as exc:
                logger.debug("ConduitBridge stop: %s", exc)
            self._browser_tool = None

    @property
    def session_cost_cents(self) -> int:
        """Return total cents spent in this session (queries ledger for accuracy)."""
        # Prefer ledger total so externally-recorded charges are included
        try:
            if self._ledger._conn is not None or True:
                ledger_total = self._ledger.session_total_cents(self._session_id)
                # Keep in-memory counter in sync
                self._session_cost_cents_total = ledger_total
                return ledger_total
        except Exception:
            pass
        return self._session_cost_cents_total

    def _charge(self, action: str, url_or_selector: str = "", success: bool = True) -> None:
        """Deduct cost for action; raise BudgetExceededError if over budget.

        Checks both the in-memory counter AND the persisted ledger total so that
        externally recorded charges (e.g. from a previous bridge instance for the
        same session) are accounted for.
        """
        cost = ACTION_COSTS.get(action.lower(), 1)
        # Query the ledger for the authoritative session total
        try:
            current_total = self._ledger.session_total_cents(self._session_id)
        except Exception:
            current_total = self._session_cost_cents_total

        if current_total + cost > self._budget_cents:
            raise BudgetExceededError(
                f"Conduit budget {self._budget_cents}¢ would be exceeded by '{action}' ({cost}¢). "
                f"Currently at {current_total}¢."
            )
        self._session_cost_cents_total = current_total + cost
        self._ledger.record(self._session_id, action, cost, url_or_selector, success)

    async def navigate(self, url: str) -> dict:
        self._charge("navigate", url_or_selector=url)
        assert self._browser_tool is not None
        result = await self._browser_tool._dispatch("navigate", {"url": url})
        if "text" in result:
            result["text"] = _strip_voix_tags(result["text"])
        # Track current URL for extract() to use
        self._current_url = result.get("url", url)
        return result

    async def click(self, selector: str) -> dict:
        self._charge("click", url_or_selector=selector)
        assert self._browser_tool is not None
        return await self._browser_tool._dispatch("click", {"selector": selector})

    async def type_text(self, selector: str, text: str) -> dict:
        self._charge("type", url_or_selector=selector)
        assert self._browser_tool is not None
        return await self._browser_tool._dispatch("type", {"selector": selector, "text": text})

    async def extract(self, selector: str = "body") -> dict:
        self._charge("extract", url_or_selector=selector)
        assert self._browser_tool is not None
        result = await self._browser_tool._dispatch("snapshot", {})
        if "text" in result:
            result["text"] = _strip_voix_tags(result["text"])
        result["char_count"] = len(result.get("text", ""))
        return result

    async def screenshot(self, path: Optional[str] = None) -> dict:
        self._charge("screenshot")
        assert self._browser_tool is not None
        kwargs: dict[str, Any] = {}
        if path:
            kwargs["filename"] = path
        return await self._browser_tool._dispatch("screenshot", kwargs)

    async def execute(self, args: dict[str, Any]) -> str:
        """Dispatch from agent_loop tool registry (same interface as BrowserTool.execute)."""
        action = args.pop("action", "") if isinstance(args, dict) else ""
        dispatch: dict[str, Any] = {
            "navigate":   lambda: self.navigate(args.get("url", "")),
            "click":      lambda: self.click(args.get("selector", "")),
            "type":       lambda: self.type_text(args.get("selector", ""), args.get("text", "")),
            "extract":    lambda: self.extract(args.get("selector", "body")),
            "screenshot": lambda: self.screenshot(args.get("path")),
        }
        handler = dispatch.get(action)
        if handler is None:
            return json.dumps({"error": f"Unknown conduit action: {action!r}. Valid: {list(dispatch)}"})
        try:
            result = await handler()
            return json.dumps(result)
        except BudgetExceededError as exc:
            return json.dumps({"error": str(exc), "budget_exceeded": True})
        except Exception as exc:
            logger.error("ConduitBridge action %s failed: %s", action, exc)
            return json.dumps({"error": str(exc), "action": action})
