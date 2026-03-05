"""
cato/tools/__init__.py — Register all built-in tools with the agent loop.

Call register_all_tools(agent_loop) once at startup to wire every tool
handler into the loop's _TOOL_REGISTRY.
"""

from .browser import BrowserTool
from .file import FileTool
from .memory import MemoryTool
from .shell import ShellTool

__all__ = ["ShellTool", "FileTool", "BrowserTool", "MemoryTool"]


def register_all_tools(agent_loop) -> None:
    """Register all tools with the module-level tool registry in agent_loop."""
    from ..agent_loop import register_tool
    register_tool("shell", ShellTool().execute)
    register_tool("file", FileTool().execute)
    register_tool("browser", BrowserTool().execute)
    register_tool("memory", MemoryTool().execute)
