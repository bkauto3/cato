"""
tests/test_pty_routes_integration.py — Integration tests for PTY REST and WebSocket.

- Creates app with PTY routes, POSTs to create session, connects WS, sends input, asserts output.
- Skips when PTY backend or CLI (claude/codex/gemini) is unavailable.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from cato.api.pty_routes import register_routes
from cato.orchestrator.pty_session import pty_available, build_pty_cmd


def _has_cli() -> bool:
    for name in ("claude", "codex", "gemini"):
        try:
            build_pty_cmd(name)
            return True
        except (ValueError, FileNotFoundError):
            continue
    return False


def make_app() -> web.Application:
    app = web.Application()
    register_routes(app)
    return app


@pytest.mark.skipif(not pty_available(), reason="PTY backend not available")
@pytest.mark.skipif(not _has_cli(), reason="No CLI (claude/codex/gemini) on PATH")
class TestPtyRoutesIntegration(AioHTTPTestCase):
    async def get_application(self):
        return make_app()

    async def test_create_session_and_ws_output(self):
        cli = "claude"
        try:
            build_pty_cmd(cli)
        except FileNotFoundError:
            cli = "codex"
            try:
                build_pty_cmd(cli)
            except FileNotFoundError:
                cli = "gemini"
                build_pty_cmd(cli)

        resp = await self.client.post(
            "/api/pty/sessions",
            json={"cli": cli},
        )
        assert resp.status == 200, await resp.text()
        data = await resp.json()
        session_id = data["session_id"]
        assert data["cli"] == cli

        received = []
        async with self.client.ws_connect(f"/ws/pty/{session_id}") as ws:
            msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
            if msg.type == web.WSMsgType.TEXT:
                obj = json.loads(msg.data)
                received.append(obj)
            await ws.send_str(json.dumps({"type": "input", "data": "help\n"}))
            for _ in range(20):
                msg = await asyncio.wait_for(ws.receive(), timeout=1.0)
                if msg.type == web.WSMsgType.TEXT:
                    obj = json.loads(msg.data)
                    received.append(obj)
                    if obj.get("type") == "output" and obj.get("data"):
                        break

        assert any(r.get("type") == "output" for r in received) or any(
            r.get("type") == "session_event" for r in received
        )

        resp2 = await self.client.get("/api/pty/sessions")
        assert resp2.status == 200
        sessions = (await resp2.json())["sessions"]
        assert not any(s["session_id"] == session_id for s in sessions)
