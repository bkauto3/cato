"""
tests/test_cursor_subagent.py

Tests for:
  - invoke_cursor_cli  (new Cursor Agent CLI invoker)
  - invoke_subagent    (backend dispatcher)
  - CatoConfig subagent fields
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cato.orchestrator.cli_invoker import (
    SubprocessError,
    invoke_cursor_cli,
    invoke_subagent,
)


# ------------------------------------------------------------------ #
# invoke_cursor_cli                                                   #
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_invoke_cursor_cli_success():
    """Happy path: cursor agent returns a non-empty response."""
    async def fake_subprocess(args, timeout_sec=90.0):
        return "Here is the refactored function [confidence: 0.82]"

    with patch("cato.orchestrator.cli_invoker._resolve_cli", return_value=["cursor"]), \
         patch("cato.orchestrator.cli_invoker._run_subprocess_async",
               side_effect=fake_subprocess):
        result = await invoke_cursor_cli("def foo(): pass", "refactor foo")

    assert result["model"] == "cursor"
    assert result["degraded"] is False
    assert result["source"] == "subprocess"
    assert "refactored" in result["response"]
    assert 0 <= result["confidence"] <= 1
    assert result["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_invoke_cursor_cli_not_installed():
    """FileNotFoundError → degraded mock response, no exception raised."""
    with patch("cato.orchestrator.cli_invoker._resolve_cli",
               side_effect=FileNotFoundError("cursor not found")):
        result = await invoke_cursor_cli("prompt", "task")

    assert result["model"] == "cursor"
    assert result["degraded"] is True
    assert result["source"] == "mock"
    assert "[Cursor Mock]" in result["response"]
    assert result["confidence"] == 0.70
    assert result["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_invoke_cursor_cli_subprocess_error():
    """Non-zero exit → degraded result with error text."""
    with patch("cato.orchestrator.cli_invoker._resolve_cli", return_value=["cursor"]), \
         patch("cato.orchestrator.cli_invoker._run_subprocess_async",
               side_effect=SubprocessError("cursor", 1, "cursor agent crashed")):
        result = await invoke_cursor_cli("prompt", "task")

    assert result["model"] == "cursor"
    assert result["degraded"] is True
    assert "cursor agent crashed" in result["response"]
    assert result["confidence"] == 0.55


@pytest.mark.asyncio
async def test_invoke_cursor_cli_timeout():
    """asyncio.TimeoutError → degraded result, no exception raised."""
    with patch("cato.orchestrator.cli_invoker._resolve_cli", return_value=["cursor"]), \
         patch("cato.orchestrator.cli_invoker._run_subprocess_async",
               side_effect=asyncio.TimeoutError()):
        result = await invoke_cursor_cli("prompt", "task")

    assert result["model"] == "cursor"
    assert result["degraded"] is True
    assert "timed out" in result["response"].lower()
    assert result["confidence"] == 0.55


@pytest.mark.asyncio
async def test_invoke_cursor_cli_empty_output_is_degraded():
    """Empty stdout from cursor agent is treated as a SubprocessError."""
    async def empty_subprocess(args, timeout_sec=90.0):
        return ""   # cursor agent returned nothing

    with patch("cato.orchestrator.cli_invoker._resolve_cli", return_value=["cursor"]), \
         patch("cato.orchestrator.cli_invoker._run_subprocess_async",
               side_effect=empty_subprocess):
        result = await invoke_cursor_cli("prompt", "task")

    assert result["model"] == "cursor"
    assert result["degraded"] is True


@pytest.mark.asyncio
async def test_invoke_cursor_cli_generic_exception():
    """Catch-all Exception handler returns degraded result without raising."""
    with patch("cato.orchestrator.cli_invoker._resolve_cli", return_value=["cursor"]), \
         patch("cato.orchestrator.cli_invoker._run_subprocess_async",
               side_effect=RuntimeError("unexpected cursor error")):
        result = await invoke_cursor_cli("prompt", "task")

    assert result["model"] == "cursor"
    assert result["degraded"] is True
    assert "unexpected cursor error" in result["response"]
    assert result["source"] == "mock"


# ------------------------------------------------------------------ #
# invoke_subagent — backend dispatch                                  #
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_invoke_subagent_dispatches_to_codex():
    """backend='codex' calls invoke_codex_cli."""
    with patch("cato.orchestrator.cli_invoker.invoke_codex_cli",
               new_callable=AsyncMock,
               return_value={"model": "codex", "response": "ok", "confidence": 0.8,
                             "latency_ms": 10, "degraded": False, "source": "pool"}) as mock_codex:
        result = await invoke_subagent("prompt", "task", backend="codex")

    mock_codex.assert_awaited_once_with("prompt", "task")
    assert result["model"] == "codex"


@pytest.mark.asyncio
async def test_invoke_subagent_dispatches_to_claude():
    """backend='claude' calls invoke_claude_api."""
    with patch("cato.orchestrator.cli_invoker.invoke_claude_api",
               new_callable=AsyncMock,
               return_value={"model": "claude", "response": "ok", "confidence": 0.9,
                             "latency_ms": 10, "degraded": False, "source": "pool"}) as mock_claude:
        result = await invoke_subagent("prompt", "task", backend="claude")

    mock_claude.assert_awaited_once_with("prompt", "task")
    assert result["model"] == "claude"


@pytest.mark.asyncio
async def test_invoke_subagent_dispatches_to_gemini():
    """backend='gemini' calls invoke_gemini_cli."""
    with patch("cato.orchestrator.cli_invoker.invoke_gemini_cli",
               new_callable=AsyncMock,
               return_value={"model": "gemini", "response": "ok", "confidence": 0.75,
                             "latency_ms": 10, "degraded": False, "source": "subprocess"}) as mock_gemini:
        result = await invoke_subagent("prompt", "task", backend="gemini")

    mock_gemini.assert_awaited_once_with("prompt", "task")
    assert result["model"] == "gemini"


@pytest.mark.asyncio
async def test_invoke_subagent_dispatches_to_cursor():
    """backend='cursor' calls invoke_cursor_cli."""
    with patch("cato.orchestrator.cli_invoker.invoke_cursor_cli",
               new_callable=AsyncMock,
               return_value={"model": "cursor", "response": "ok", "confidence": 0.80,
                             "latency_ms": 15, "degraded": False, "source": "subprocess"}) as mock_cursor:
        result = await invoke_subagent("prompt", "task", backend="cursor")

    mock_cursor.assert_awaited_once_with("prompt", "task")
    assert result["model"] == "cursor"


@pytest.mark.asyncio
async def test_invoke_subagent_unknown_backend_falls_back_to_codex():
    """Unknown backend string falls back to codex without raising."""
    with patch("cato.orchestrator.cli_invoker.invoke_codex_cli",
               new_callable=AsyncMock,
               return_value={"model": "codex", "response": "fallback", "confidence": 0.7,
                             "latency_ms": 5, "degraded": False, "source": "subprocess"}) as mock_codex:
        result = await invoke_subagent("prompt", "task", backend="chatgpt")  # type: ignore[arg-type]

    mock_codex.assert_awaited_once()
    assert result["model"] == "codex"


# ------------------------------------------------------------------ #
# CatoConfig subagent fields                                         #
# ------------------------------------------------------------------ #

def test_config_subagent_defaults():
    """subagent_enabled=False, subagent_coding_backend='codex' by default."""
    from cato.config import CatoConfig
    cfg = CatoConfig()
    assert cfg.subagent_enabled is False
    assert cfg.subagent_coding_backend == "codex"


def test_config_subagent_fields_persist_round_trip(tmp_path):
    """Saving and reloading config preserves subagent fields."""
    from cato.config import CatoConfig
    cfg_path = tmp_path / "config.yaml"
    cfg = CatoConfig()
    cfg.subagent_enabled = True
    cfg.subagent_coding_backend = "cursor"
    cfg.save(config_path=cfg_path)

    loaded = CatoConfig.load(config_path=cfg_path)
    assert loaded.subagent_enabled is True
    assert loaded.subagent_coding_backend == "cursor"


def test_config_subagent_all_backends_accepted(tmp_path):
    """Each supported backend string round-trips correctly."""
    from cato.config import CatoConfig
    for backend in ("claude", "codex", "gemini", "cursor"):
        cfg_path = tmp_path / f"config_{backend}.yaml"
        cfg = CatoConfig()
        cfg.subagent_enabled = True
        cfg.subagent_coding_backend = backend
        cfg.save(config_path=cfg_path)
        loaded = CatoConfig.load(config_path=cfg_path)
        assert loaded.subagent_coding_backend == backend
